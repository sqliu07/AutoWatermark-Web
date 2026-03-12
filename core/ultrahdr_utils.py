#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultra HDR (JPEG_R) helper utilities.

Key ideas:
- Ultra HDR stores an SDR "Primary" JPEG plus a secondary "GainMap" JPEG appended after the primary EOI.
- The primary JPEG contains XMP (GContainer directory) that describes the appended item(s).
- The gain map JPEG contains XMP (hdrgm namespace) with parameters like GainMapMin/Max/Gamma.

This module provides:
- split_ultrahdr(): extract primary and gainmap JPEG bytes
- pack_ultrahdr(): build a JPEG_R file from primary+gainmap and XMP
- expand_gainmap_for_borders(): if you enlarge the primary (add borders), pad the gainmap with neutral pixels
- small XMP helpers (strip/inject/update directory lengths)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from PIL import Image

XMP_APP1_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
HDRGM_NS = "http://ns.adobe.com/hdr-gain-map/1.0/"

# ---- JPEG parsing helpers ----
def _read_u16_be(data: bytes, off: int) -> int:
    return (data[off] << 8) | data[off + 1]

def _find_next_marker(data: bytes, off: int) -> Optional[Tuple[int, int]]:
    n = len(data)
    i = off
    while i + 1 < n:
        if data[i] == 0xFF:
            j = i + 1
            while j < n and data[j] == 0xFF:
                j += 1
            if j >= n:
                return None
            if data[j] == 0x00:  # stuffed
                i = j + 1
                continue
            marker = (0xFF << 8) | data[j]
            return marker, i
        i += 1
    return None

def find_end_of_jpeg(data: bytes, start: int = 0) -> int:
    if start + 1 >= len(data) or data[start:start + 2] != b"\xFF\xD8":
        raise ValueError("Not a JPEG SOI at given start offset")

    off = start + 2
    while True:
        mk = _find_next_marker(data, off)
        if mk is None:
            raise ValueError("EOI not found")
        marker, mpos = mk

        if marker == 0xFFD9:  # EOI
            return mpos + 2

        if 0xFFD0 <= marker <= 0xFFD7 or marker in (0xFFD8, 0xFF01):
            off = mpos + 2
            continue

        if marker == 0xFFDA:  # SOS
            if mpos + 4 > len(data):
                raise ValueError("Truncated SOS")
            seglen = _read_u16_be(data, mpos + 2)
            off = mpos + 2 + seglen
            continue

        if mpos + 4 > len(data):
            raise ValueError("Truncated segment")
        seglen = _read_u16_be(data, mpos + 2)
        if seglen < 2:
            raise ValueError("Invalid segment length")
        off = mpos + 2 + seglen

def iter_app1_xmp_packets(jpeg_bytes: bytes) -> List[bytes]:
    """Return list of raw XMP XML (without the APP1 XMP header)."""
    if jpeg_bytes[:2] != b"\xFF\xD8":
        return []
    packets: List[bytes] = []
    off = 2
    n = len(jpeg_bytes)
    while off + 4 <= n:
        mk = _find_next_marker(jpeg_bytes, off)
        if mk is None:
            break
        marker, mpos = mk
        if marker in (0xFFDA, 0xFFD9):
            break
        if 0xFFD0 <= marker <= 0xFFD7 or marker in (0xFFD8, 0xFF01):
            off = mpos + 2
            continue

        seglen = _read_u16_be(jpeg_bytes, mpos + 2)
        payload_start = mpos + 4
        payload_end = mpos + 2 + seglen
        if payload_end > n:
            break

        if marker == 0xFFE1:  # APP1
            payload = jpeg_bytes[payload_start:payload_end]
            if payload.startswith(XMP_APP1_HEADER):
                packets.append(payload[len(XMP_APP1_HEADER):])

        off = payload_end
    return packets

def _strip_xmp(jpeg_bytes: bytes) -> bytes:
    """Remove APP1 XMP segments only (keeps EXIF APP1)."""
    if not jpeg_bytes.startswith(b"\xff\xd8"):
        raise ValueError("Input is not a JPEG")
    out = bytearray(jpeg_bytes[:2])
    idx = 2
    n = len(jpeg_bytes)
    while idx < n:
        if jpeg_bytes[idx] != 0xFF:
            out.extend(jpeg_bytes[idx:])
            break

        j = idx + 1
        while j < n and jpeg_bytes[j] == 0xFF:
            j += 1
        if j >= n:
            break

        marker = (0xFF << 8) | jpeg_bytes[j]
        out.extend(jpeg_bytes[idx:j + 2])
        idx = j + 2

        if marker == 0xFFD9:
            break
        if 0xFFD0 <= marker <= 0xFFD7 or marker in (0xFFD8, 0xFF01):
            continue
        if marker == 0xFFDA:
            out.extend(jpeg_bytes[idx:])
            break

        if idx + 2 > n:
            break
        seglen = _read_u16_be(jpeg_bytes, idx)
        seg_start = idx - 2
        seg_end = idx + seglen
        if seg_end > n:
            break

        payload = jpeg_bytes[idx + 2:seg_end]
        if marker == 0xFFE1 and payload.startswith(XMP_APP1_HEADER):
            # remove this segment: roll back marker bytes we just wrote
            out = out[:-2]
        else:
            out.extend(jpeg_bytes[idx:seg_end])

        idx = seg_end
    return bytes(out)

def _build_xmp_segment(xmp_xml: bytes) -> bytes:
    payload = XMP_APP1_HEADER + xmp_xml
    seglen = len(payload) + 2
    if seglen > 0xFFFF:
        raise ValueError("XMP too large for one APP1 segment")
    return b"\xFF\xE1" + bytes([(seglen >> 8) & 0xFF, seglen & 0xFF]) + payload

def inject_xmp(jpeg_bytes: bytes, xmp_xml: bytes) -> bytes:
    """Strip existing XMP then inject XMP right after SOI."""
    stripped = _strip_xmp(jpeg_bytes)
    return stripped[:2] + _build_xmp_segment(xmp_xml) + stripped[2:]

# ---- GContainer parsing / updating ----
def parse_gcontainer_items_from_xmp(xmp_xml_bytes: bytes) -> Optional[List[Dict]]:
    try:
        text = xmp_xml_bytes.decode("utf-8", errors="replace")
        root = ET.fromstring(text)
    except Exception:
        return None

    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "Container": "http://ns.google.com/photos/1.0/container/",
        "Item": "http://ns.google.com/photos/1.0/container/item/",
    }

    items: List[Dict] = []
    for ci in root.findall(".//Container:Directory//Container:Item", ns):
        sem = ci.attrib.get(f"{{{ns['Item']}}}Semantic")
        length = ci.attrib.get(f"{{{ns['Item']}}}Length")
        padding = ci.attrib.get(f"{{{ns['Item']}}}Padding")
        mime = ci.attrib.get(f"{{{ns['Item']}}}Mime")
        uri = ci.attrib.get(f"{{{ns['Item']}}}URI")
        if sem or length or padding or mime or uri:
            items.append(
                {
                    "semantic": sem,
                    "mime": mime,
                    "length": int(length) if (length and length.isdigit()) else None,
                    "padding": int(padding) if (padding and padding.isdigit()) else 0,
                    "uri": uri,
                }
            )
    return items or None

def _update_container_item_length(xmp_text: str, semantic: str, new_length: int) -> str:
    """
    Update (or insert) Item:Length for the <Container:Item ... Item:Semantic="..."> element.
    """
    # Match the tag itself.
    pattern = re.compile(r'(<Container:Item\b[^>]*\bItem:Semantic="%s"[^>]*)(/?>)' % re.escape(semantic))
    m = pattern.search(xmp_text)
    if not m:
        return xmp_text

    tag_head = m.group(1)
    tag_tail = m.group(2)

    if re.search(r'\bItem:Length="\d+"', tag_head):
        tag_head = re.sub(r'(Item:Length=")\d+(")', r'\g<1>%d\2' % new_length, tag_head, count=1)
    else:
        tag_head = tag_head + f' Item:Length="{new_length}"'

    # Tightly packed (recommended by spec)
    if re.search(r'\bItem:Padding="\d+"', tag_head):
        tag_head = re.sub(r'(Item:Padding=")\d+(")', r'\g<1>0\2', tag_head, count=1)
    else:
        tag_head = tag_head + ' Item:Padding="0"'

    return xmp_text[:m.start()] + tag_head + tag_tail + xmp_text[m.end():]

def update_primary_xmp_lengths(primary_xmp: bytes, primary_len: int, gainmap_len: int) -> bytes:
    """
    Update GContainer Directory lengths for Primary and GainMap.
    Keeps the rest of XMP unchanged.
    """
    text = primary_xmp.decode("utf-8", errors="ignore")
    text2 = _update_container_item_length(text, "Primary", primary_len)
    text2 = _update_container_item_length(text2, "GainMap", gainmap_len)
    return text2.encode("utf-8")

def looks_like_ultrahdr(primary_jpeg: bytes) -> bool:
    # Android spec: hdrgm:Version="1.0" in primary XMP is a signal; also GContainer GainMap semantic.
    if b"http://ns.adobe.com/hdr-gain-map/1.0/" in primary_jpeg or b'hdrgm:Version="1.0"' in primary_jpeg:
        return True
    if b'Item:Semantic="GainMap"' in primary_jpeg or b"DirectoryItemSemantic>GainMap" in primary_jpeg:
        return True
    return False

# ---- Gain map metadata + neutral fill ----

@dataclass
class GainMapParams:
    gain_map_min_log2: float = 0.0
    gain_map_max_log2: float = 0.0
    gamma: float = 1.0

def parse_gainmap_params_from_xmp(gainmap_xmp: bytes) -> GainMapParams:
    """
    Parse hdrgm:GainMapMin / hdrgm:GainMapMax / hdrgm:Gamma (single scalar only).
    """
    text = gainmap_xmp.decode("utf-8", errors="ignore")

    def get_float(attr: str, default: float) -> float:
        m = re.search(rf'{re.escape(attr)}="([^"]+)"', text)
        if not m:
            return default
        try:
            return float(m.group(1))
        except Exception:
            return default

    return GainMapParams(
        gain_map_min_log2=get_float("hdrgm:GainMapMin", 0.0),
        gain_map_max_log2=get_float("hdrgm:GainMapMax", 0.0),
        gamma=get_float("hdrgm:Gamma", 1.0),
    )

def neutral_encoded_recovery_for_gain_1(params: GainMapParams) -> int:
    """
    Compute encoded_recovery value that corresponds to pixel_gain = 1.0.

    From Android Ultra HDR spec:
      map_min_log2 = log2(min_content_boost)
      map_max_log2 = log2(max_content_boost)
      log_recovery = (log2(pixel_gain) - map_min_log2) / (map_max_log2 - map_min_log2)
      recovery = pow(clamp(log_recovery,0,1), map_gamma)
      encoded = round(recovery * 255)
    """
    mn = params.gain_map_min_log2
    mx = params.gain_map_max_log2
    g = params.gamma if params.gamma > 0 else 1.0
    if mx == mn:
        return 0
    # pixel_gain=1 -> log2(pixel_gain)=0
    log_recovery = (0.0 - mn) / (mx - mn)
    log_recovery = min(1.0, max(0.0, log_recovery))
    recovery = pow(log_recovery, g)
    enc = int(recovery * 255.0 + 0.5)
    return min(255, max(0, enc))

# ---- Split / Pack ----

@dataclass
class UltraHDRParts:
    primary_jpeg: bytes
    gainmap_jpeg: bytes
    primary_xmp: Optional[bytes]
    gainmap_xmp: Optional[bytes]
    primary_len: int

def _scan_appended_jpegs(data: bytes, start_off: int) -> List[Tuple[int, int]]:
    res: List[Tuple[int, int]] = []
    i = start_off
    while True:
        pos = data.find(b"\xFF\xD8", i)
        if pos < 0:
            break
        try:
            end = find_end_of_jpeg(data, pos)
            res.append((pos, end))
            i = end
        except Exception:
            i = pos + 2
    return res

def _looks_like_gainmap(jpeg_bytes: bytes) -> bool:
    if b"http://ns.adobe.com/hdr-gain-map/1.0/" in jpeg_bytes or b"hdrgm:GainMap" in jpeg_bytes:
        return True
    for pkt in iter_app1_xmp_packets(jpeg_bytes):
        if b"http://ns.adobe.com/hdr-gain-map/1.0/" in pkt or b"hdrgm:Version" in pkt:
            return True
    return False

def split_ultrahdr(file_bytes: bytes) -> UltraHDRParts:
    base_end = find_end_of_jpeg(file_bytes, 0)
    primary = file_bytes[:base_end]
    tail = file_bytes[base_end:]

    primary_xmp = None
    pkts = iter_app1_xmp_packets(primary)
    if pkts:
        primary_xmp = pkts[0]

    gainmap_bytes: Optional[bytes] = None
    gainmap_xmp: Optional[bytes] = None

    # Prefer GContainer semantic + length if present
    items = None
    if pkts:
        for pkt in pkts:
            items = parse_gcontainer_items_from_xmp(pkt)
            if items:
                break

    if items:
        # compute offsets: primary length is base_end (primary item ends at EOI)
        cur = base_end
        for it in items:
            if it.get("semantic") == "Primary":
                continue
            ln = it.get("length")
            pad = it.get("padding") or 0
            if it.get("semantic") == "GainMap" and ln:
                gainmap_bytes = file_bytes[cur:cur + ln]
                break
            if ln:
                cur += ln + pad

    # Fallback scan
    if gainmap_bytes is None:
        appended = _scan_appended_jpegs(file_bytes, base_end)
        candidates = [file_bytes[o:e] for o, e in appended]
        gm = next((c for c in candidates if _looks_like_gainmap(c)), None)
        gainmap_bytes = gm or (candidates[0] if candidates else None)

    if gainmap_bytes is None:
        raise ValueError("Could not locate GainMap JPEG in file")

    gm_pkts = iter_app1_xmp_packets(gainmap_bytes)
    if gm_pkts:
        gainmap_xmp = gm_pkts[0]

    return UltraHDRParts(
        primary_jpeg=primary,
        gainmap_jpeg=gainmap_bytes,
        primary_xmp=primary_xmp,
        gainmap_xmp=gainmap_xmp,
        primary_len=len(primary),
    )

def pack_ultrahdr(primary_jpeg: bytes, gainmap_jpeg: bytes, primary_xmp: bytes) -> bytes:
    primary_with_xmp = inject_xmp(primary_jpeg, primary_xmp)
    return primary_with_xmp + gainmap_jpeg

# ---- Gainmap padding for watermark/borders ----
def expand_gainmap_for_borders(
    *,
    orig_gainmap_jpeg: bytes,
    orig_gainmap_xmp: bytes,
    orig_primary_size: Tuple[int, int],
    new_primary_size: Tuple[int, int],
    content_box: Tuple[int, int, int, int],
) -> bytes:
    """
    If you enlarged the primary image (e.g. add borders/footer), expand the gain map so that:
    - The original gainmap still maps to the original content region
    - The newly-added border region has pixel_gain=1.0 (neutral)

    The mapping assumes viewers sample the gain map over normalized coordinates (spec allows different resolution).
    """
    (bw, bh) = orig_primary_size
    (nw, nh) = new_primary_size
    left_px, top_px, _, _ = content_box

    # Decode gainmap JPEG to image
    gm_img = Image.open(BytesIO(orig_gainmap_jpeg))
    gm_img.load()

    # Gain map is defined as single-channel; but it may be stored as RGB JPEG.
    # We'll work in L then save as grayscale JPEG.
    gm_rgb = gm_img.convert("RGB")
    gw, gh = gm_rgb.size

    # Compute new gainmap canvas size so aspect matches new primary, preserving normalized mapping
    new_gw = max(1, int(round(gw * (nw / bw))))
    new_gh = max(1, int(round(gh * (nh / bh))))

    # Compute padding in gainmap pixel space
    pad_x = int(round(left_px * (gw / bw)))
    pad_y = int(round(top_px * (gh / bh)))

    # Neutral fill value from gainmap XMP
    params = parse_gainmap_params_from_xmp(orig_gainmap_xmp)
    neutral = neutral_encoded_recovery_for_gain_1(params)

    canvas = Image.new("L", (new_gw, new_gh), color=neutral)
    canvas.paste(gm_rgb, (pad_x, pad_y))

    # Re-encode JPEG (quality not too low to avoid banding)
    out = BytesIO()
    canvas.save(out, format="JPEG", quality=100, optimize=False)

    # Ensure the required hdrgm XMP stays in the gainmap JPEG
    return inject_xmp(out.getvalue(), orig_gainmap_xmp)
