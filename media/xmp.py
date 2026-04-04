"""XMP 元数据解析与注入工具。"""

from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "XMP_START_MARKER",
    "XMP_END_MARKER",
    "XMP_HEADER",
    "MICRO_VIDEO_OFFSET_PATTERN",
    "MICRO_VIDEO_LENGTH_PATTERN",
    "MOTIONPHOTO_FLAG_PATTERN",
    "OFFSET_ATTRS",
    "LENGTH_ATTRS",
    "_extract_xmp_segment",
    "_parse_first_match",
    "_looks_like_motionphoto_flag",
    "_update_container_directory_lengths",
    "_ensure_container_namespaces",
    "_detect_motion_video_mime",
    "_ensure_hdrgm_namespace_and_version",
    "_set_container_directory_ultrahdr_motion",
    "_prepare_xmp_ultrahdr_motion",
    "_prepare_xmp",
    "_update_attribute_if_exists",
    "_ensure_offset_length_attrs",
    "_strip_existing_xmp",
    "_build_xmp_segment",
    "_inject_xmp",
]

XMP_START_MARKER = b"<x:xmpmeta"
XMP_END_MARKER = b"</x:xmpmeta>"
XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"

MICRO_VIDEO_OFFSET_PATTERN = re.compile(
    rb'(?:GCamera:MicroVideoOffset|GCamera:MotionPhotoOffset|Camera:MotionPhotoOffset)="(\d+)"'
)
MICRO_VIDEO_LENGTH_PATTERN = re.compile(
    rb'(?:GCamera:MicroVideoLength|GCamera:MotionPhotoLength|Camera:MotionPhotoLength)="(\d+)"'
)

# Xiaomi / generic: MotionPhoto : 1 but without explicit offset/length
MOTIONPHOTO_FLAG_PATTERN = re.compile(
    rb'(?:GCamera:MotionPhoto|Camera:MotionPhoto|MotionPhoto)\s*=\s*"?1"?'
)

OFFSET_ATTRS = [
    "GCamera:MicroVideoOffset",
    "GCamera:MotionPhotoOffset",
    "Camera:MotionPhotoOffset",
]

LENGTH_ATTRS = [
    "GCamera:MicroVideoLength",
    "GCamera:MotionPhotoLength",
    "Camera:MotionPhotoLength",
]


def _extract_xmp_segment(data: bytes) -> Optional[bytes]:
    start = data.find(XMP_START_MARKER)
    if start == -1:
        return None
    end = data.find(XMP_END_MARKER, start)
    if end == -1:
        return None
    end += len(XMP_END_MARKER)
    return data[start:end]


def _parse_first_match(pattern: re.Pattern[bytes], data: bytes) -> Optional[int]:
    match = pattern.search(data)
    if match:
        return int(match.group(1))
    return None


def _looks_like_motionphoto_flag(xmp: bytes) -> bool:
    return MOTIONPHOTO_FLAG_PATTERN.search(xmp) is not None


def _update_container_directory_lengths(xmp_text: str, video_length: int) -> str:
    """
    Motion Photo format 1.0: update Container:Directory's MotionPhoto video item's Item:Length
    so readers can locate the appended video reliably.
    Also force Primary item's Item:Padding to 0 (we pack JPEG+video tightly).
    """
    def repl(m: re.Match[str]) -> str:
        tag = m.group(1)

        # If this is the primary item, we pack tightly -> padding should be 0 if present
        if 'Item:Semantic="Primary"' in tag:
            tag = re.sub(r'(Item:Padding=")(\d+)(")', r'\g<1>0\g<3>', tag)

        # If this is the motion video item, update its length
        is_motion = ('Item:Semantic="MotionPhoto"' in tag)
        is_video = ('Item:Mime="video/' in tag)  # video/mp4 or video/quicktime
        if is_motion or is_video:
            if 'Item:Length="' in tag:
                tag = re.sub(
                    r'(Item:Length=")(\d+)(")',
                    rf'\g<1>{video_length}\g<3>',
                    tag,
                )
        return tag

    # Replace each <Container:Item ...> tag independently
    return re.sub(r'(<Container:Item\b[^>]*>)', repl, xmp_text)


def _ensure_container_namespaces(xmp_text: str) -> str:
    """
    If a file uses Motion Photo format 1.0 container directory, it should have these namespaces.
    We only add them if Container:Directory exists but namespaces are missing.
    """
    if "Container:Directory" not in xmp_text:
        return xmp_text

    # Ensure Container namespace
    if "xmlns:Container=" not in xmp_text:
        xmp_text = re.sub(
            r"(<rdf:Description\b)",
            r'\1 xmlns:Container="http://ns.google.com/photos/1.0/container/"',
            xmp_text,
            count=1,
        )

    # Ensure Item namespace
    if "xmlns:Item=" not in xmp_text:
        xmp_text = re.sub(
            r"(<rdf:Description\b)",
            r'\1 xmlns:Item="http://ns.google.com/photos/1.0/container/item/"',
            xmp_text,
            count=1,
        )

    return xmp_text

def _detect_motion_video_mime(xmp_text: str) -> str:
    m = re.search(r'Item:Semantic="MotionPhoto"[^>]*Item:Mime="([^"]+)"', xmp_text)
    if m:
        return m.group(1)
    m = re.search(r'Item:Mime="(video/[^"]+)"', xmp_text)
    if m:
        return m.group(1)
    return "video/mp4"


def _ensure_hdrgm_namespace_and_version(xmp_text: str) -> str:
    # Ensure hdrgm namespace
    if "xmlns:hdrgm=" not in xmp_text:
        xmp_text = re.sub(
            r"(<rdf:Description\b)",
            r'\1 xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/"',
            xmp_text,
            count=1,
        )
    # Ensure hdrgm:Version="1.0"
    if 'hdrgm:Version="' not in xmp_text:
        xmp_text, _ = re.subn(
            r"(<rdf:Description\b[^>]*)(>)",
            r'\1 hdrgm:Version="1.0"\2',
            xmp_text,
            count=1,
        )
    return xmp_text


def _set_container_directory_ultrahdr_motion(
    xmp_text: str,
    primary_length: int,
    gainmap_length: int,
    video_length: int,
    video_mime: str,
) -> str:
    # Rebuild directory to guarantee item order: Primary -> GainMap -> MotionPhoto (video last)
    directory = (
        "      <Container:Directory>\n"
        "        <rdf:Seq>\n"
        '          <rdf:li rdf:parseType="Resource">\n'
        f'            <Container:Item Item:Semantic="Primary" Item:Mime="image/jpeg" Item:Length="{primary_length}" Item:Padding="0"/>\n'
        "          </rdf:li>\n"
        '          <rdf:li rdf:parseType="Resource">\n'
        f'            <Container:Item Item:Semantic="GainMap" Item:Mime="image/jpeg" Item:Length="{gainmap_length}" Item:Padding="0"/>\n'
        "          </rdf:li>\n"
        '          <rdf:li rdf:parseType="Resource">\n'
        f'            <Container:Item Item:Semantic="MotionPhoto" Item:Mime="{video_mime}" Item:Length="{video_length}" Item:Padding="0"/>\n'
        "          </rdf:li>\n"
        "        </rdf:Seq>\n"
        "      </Container:Directory>\n"
    )

    if "Container:Directory" in xmp_text:
        xmp_text, n = re.subn(
            r"<Container:Directory>.*?</Container:Directory>",
            directory.rstrip("\n"),
            xmp_text,
            flags=re.DOTALL,
            count=1,
        )
        if n > 0:
            return xmp_text

    # If no Container:Directory block, insert into first rdf:Description body
    xmp_text, _ = re.subn(
        r"(<rdf:Description\b[^>]*>)",
        r"\1\n" + directory,
        xmp_text,
        count=1,
    )
    return xmp_text


def _prepare_xmp_ultrahdr_motion(
    xmp_bytes: bytes,
    *,
    primary_length: int,
    gainmap_length: int,
    video_length: int,
) -> bytes:
    # Start from your existing motion photo updates (legacy attrs + motion item length updates)
    xmp_text = _prepare_xmp(xmp_bytes, video_length).decode("utf-8", errors="ignore")

    # Ensure namespaces for Container/Item (you already have this helper)
    xmp_text = _ensure_container_namespaces(xmp_text)

    # Ensure hdrgm on primary XMP so viewers treat it as Ultra HDR
    xmp_text = _ensure_hdrgm_namespace_and_version(xmp_text)

    # Detect original video mime if present, else default
    video_mime = _detect_motion_video_mime(xmp_text)

    # Rebuild Container:Directory with correct order and lengths
    xmp_text = _set_container_directory_ultrahdr_motion(
        xmp_text,
        primary_length=primary_length,
        gainmap_length=gainmap_length,
        video_length=video_length,
        video_mime=video_mime,
    )

    return xmp_text.encode("utf-8")

def _prepare_xmp(xmp_bytes: bytes, video_length: int) -> bytes:
    """
    Update motion photo metadata to match the *new* appended video length.

    - Update legacy offset/length attributes if present.
    - If file declares MotionPhoto=1 but lacks boundaries, inject GCamera:*Offset/*Length.
    - If file contains Motion Photo format 1.0 Container:Directory, update the motion item's Item:Length.
    """
    xmp_text = xmp_bytes.decode("utf-8", errors="ignore")

    # --- A) Legacy/compat attrs ---
    for attr in OFFSET_ATTRS:
        xmp_text = _update_attribute_if_exists(xmp_text, attr, str(video_length))
    for attr in LENGTH_ATTRS:
        xmp_text = _update_attribute_if_exists(xmp_text, attr, str(video_length))

    # --- B) Xiaomi-style (MotionPhoto=1 but no explicit offset/length): inject a compatible set ---
    if (_looks_like_motionphoto_flag(xmp_bytes)
        and not any(f'{a}="' in xmp_text for a in OFFSET_ATTRS + LENGTH_ATTRS)):
        xmp_text = _ensure_offset_length_attrs(xmp_text, video_length)

    # --- C) Motion Photo format 1.0 container directory: MUST update Item:Length for the motion item ---
    # This is likely why Xiaomi album doesn't recognize (DirectoryItemLength mismatch).
    xmp_text = _ensure_container_namespaces(xmp_text)
    xmp_text = _update_container_directory_lengths(xmp_text, video_length)

    return xmp_text.encode("utf-8")


def _update_attribute_if_exists(xmp_text: str, attr: str, value: str) -> str:
    pattern = re.compile(rf'({re.escape(attr)}=")([^"]+)(")')
    if pattern.search(xmp_text):
        return pattern.sub(rf"\g<1>{value}\g<3>", xmp_text)
    return xmp_text


def _ensure_offset_length_attrs(xmp_text: str, video_length: int) -> str:
    """
    Inject GCamera MotionPhoto/MicroVideo offset/length attributes into the first rdf:Description tag.
    This is a pragmatic compatibility hack for vendors that only set MotionPhoto=1 but omit boundaries.
    """
    # Ensure namespace
    if "xmlns:GCamera=" not in xmp_text:
        xmp_text = re.sub(
            r"(<rdf:Description\b)",
            r'\1 xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"',
            xmp_text,
            count=1,
        )

    insert = (
        f' GCamera:MotionPhotoOffset="{video_length}"'
        f' GCamera:MotionPhotoLength="{video_length}"'
        f' GCamera:MicroVideoOffset="{video_length}"'
        f' GCamera:MicroVideoLength="{video_length}"'
    )

    # Insert before the closing '>' of the first rdf:Description start tag
    xmp_text, n = re.subn(r"(<rdf:Description\b[^>]*)(>)", r"\1" + insert + r"\2", xmp_text, count=1)
    return xmp_text


def _strip_existing_xmp(jpeg_bytes: bytes) -> bytes:
    if not jpeg_bytes.startswith(b"\xff\xd8"):
        raise ValueError("Input is not a JPEG file")

    output = bytearray()
    output.extend(jpeg_bytes[:2])
    idx = 2

    while idx < len(jpeg_bytes):
        if jpeg_bytes[idx] != 0xFF:
            output.extend(jpeg_bytes[idx:])
            break

        marker = jpeg_bytes[idx:idx + 2]
        if marker == b"\xff\xda":
            output.extend(jpeg_bytes[idx:])
            break

        if idx + 4 > len(jpeg_bytes):
            output.extend(jpeg_bytes[idx:])
            break

        seg_length = int.from_bytes(jpeg_bytes[idx + 2:idx + 4], "big")
        segment = jpeg_bytes[idx:idx + 2 + seg_length]

        if marker == b"\xff\xe1" and segment[4:4 + len(XMP_HEADER)] == XMP_HEADER:
            idx += 2 + seg_length
            continue

        output.extend(segment)
        idx += 2 + seg_length

    return bytes(output)


def _build_xmp_segment(xmp_bytes: bytes) -> bytes:
    payload = XMP_HEADER + xmp_bytes
    length = len(payload) + 2
    return b"\xff\xe1" + length.to_bytes(2, "big") + payload


def _inject_xmp(jpeg_bytes: bytes, xmp_bytes: bytes) -> bytes:
    stripped = _strip_existing_xmp(jpeg_bytes)
    return stripped[:2] + _build_xmp_segment(xmp_bytes) + stripped[2:]
