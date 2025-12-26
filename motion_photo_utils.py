from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


@dataclass
class _RawMotionComponents:
    photo_bytes: bytes
    video_bytes: bytes
    xmp_bytes: Optional[bytes]


@dataclass
class MotionPhotoSession:
    still_path: Path
    video_bytes: bytes
    xmp_bytes: bytes
    _workspace: tempfile.TemporaryDirectory

    @property
    def has_motion(self) -> bool:
        return bool(self.video_bytes)

    def finalize(self, watermarked_path: Path, output_path: Path, metadata: dict) -> None:
        """
        watermarked_path: path to the watermarked STILL jpeg (already rendered by your watermark pipeline)
        output_path: final motion photo path to write
        metadata: must contain overlay_image (PIL image) and content_box (left,top,right,bottom)
        """
        if not self.has_motion:
            raise ValueError("Cannot finalize motion photo without video bytes")
        if not self.xmp_bytes:
            raise ValueError("Missing XMP metadata for motion photo reassembly")
        if not metadata:
            raise ValueError("Watermark metadata required for motion photo processing")

        overlay_image = metadata.get("overlay_image")
        content_box = metadata.get("content_box")
        if overlay_image is None or content_box is None:
            raise ValueError("Incomplete watermark metadata for motion photo processing")

        workspace_path = Path(self._workspace.name)

        # --- 1) Watermark the appended video using ffmpeg ---
        original_video_path = workspace_path / "motion_original.mp4"
        original_video_path.write_bytes(self.video_bytes)

        overlay_path = workspace_path / "watermark_overlay.png"
        overlay_image.save(overlay_path, format="PNG")

        watermarked_video_path = workspace_path / "motion_watermarked.mp4"
        _apply_watermark_to_video(
            original_video_path,
            overlay_path,
            watermarked_video_path,
            content_box,
            overlay_size=overlay_image.size,  # (w, h)
        )
        watermarked_video_bytes = watermarked_video_path.read_bytes()

        # --- 2) IMPORTANT: preserve EXIF/MakerNote metadata on still image (Xiaomi album may rely on it) ---
        # Copy metadata from original still (extracted from original motion file) to the watermarked still jpeg.
        # If exiftool not installed, this step is skipped.
        _copy_all_metadata_with_exiftool(self.still_path, Path(watermarked_path))

        # --- 3) Inject/Update XMP so album can locate the appended video tail ---
        jpeg_with_xmp = _inject_xmp(
            Path(watermarked_path).read_bytes(),
            _prepare_xmp(self.xmp_bytes, len(watermarked_video_bytes)),
        )

        # --- 4) Reassemble: JPEG(still+XMP) + MP4 tail ---
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(jpeg_with_xmp + watermarked_video_bytes)

    def cleanup(self) -> None:
        self._workspace.cleanup()


def prepare_motion_photo(image_path: str | Path) -> Optional[MotionPhotoSession]:
    path = Path(image_path)
    data = path.read_bytes()
    components = _split_motion_photo(data)
    if not components.video_bytes or not components.xmp_bytes:
        return None

    workspace = tempfile.TemporaryDirectory()
    still_path = Path(workspace.name) / f"{path.stem}_motion_still.jpg"
    still_path.write_bytes(components.photo_bytes)

    return MotionPhotoSession(
        still_path=still_path,
        video_bytes=components.video_bytes,
        xmp_bytes=components.xmp_bytes,
        _workspace=workspace,
    )


def _split_motion_photo(data: bytes) -> _RawMotionComponents:
    xmp = _extract_xmp_segment(data)
    if not xmp:
        return _RawMotionComponents(photo_bytes=data, video_bytes=b"", xmp_bytes=None)

    length = _parse_first_match(MICRO_VIDEO_LENGTH_PATTERN, xmp)
    offset = _parse_first_match(MICRO_VIDEO_OFFSET_PATTERN, xmp)

    file_size = len(data)

    # 1) Old style: length/offset describes appended video tail
    if length and length > 0:
        video_length = length
        video_start = file_size - video_length
        if 0 < video_start < file_size:
            photo_bytes = data[:video_start]
            video_bytes = data[video_start:video_start + video_length]
            if _mp4_looks_valid(video_bytes):
                return _RawMotionComponents(photo_bytes=photo_bytes, video_bytes=video_bytes, xmp_bytes=xmp)

    if offset and offset > 0:
        video_length = offset
        video_start = file_size - video_length
        if 0 < video_start < file_size:
            photo_bytes = data[:video_start]
            video_bytes = data[video_start:video_start + video_length]
            if _mp4_looks_valid(video_bytes):
                return _RawMotionComponents(photo_bytes=photo_bytes, video_bytes=video_bytes, xmp_bytes=xmp)

    # 2) Xiaomi / generic: MotionPhoto=1 but no explicit offset/length.
    #    Fall back to scanning file tail for MP4 box 'ftyp' to locate video start.
    if _looks_like_motionphoto_flag(xmp):
        start = _find_mp4_start_by_ftyp(data)
        if start is not None and 0 < start < file_size:
            photo_bytes = data[:start]
            video_bytes = data[start:]
            if _mp4_looks_valid(video_bytes):
                return _RawMotionComponents(photo_bytes=photo_bytes, video_bytes=video_bytes, xmp_bytes=xmp)

    return _RawMotionComponents(photo_bytes=data, video_bytes=b"", xmp_bytes=xmp)


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


def _mp4_looks_valid(video_bytes: bytes) -> bool:
    head = video_bytes[:65536]
    return b"ftyp" in head


def _find_mp4_start_by_ftyp(data: bytes, scan_tail_bytes: int = 32 * 1024 * 1024) -> Optional[int]:
    """
    Scan the tail of file to locate MP4 start by finding 'ftyp' box.
    Typical MP4 starts with: [4-byte size][b'ftyp']...
    Many motion photos are: JPEG ... FFD9 ... MP4...
    """
    n = len(data)
    if n < 16:
        return None

    tail = data[max(0, n - scan_tail_bytes):]
    base = n - len(tail)

    idx = tail.rfind(b"ftyp")
    while idx != -1:
        if idx >= 4:
            start = base + idx - 4
            if start >= 0 and start + 8 <= n and data[start + 4:start + 8] == b"ftyp":
                size = int.from_bytes(data[start:start + 4], "big", signed=False)
                if 8 <= size <= (n - start):
                    # Prefer JPEG EOI + 2 if close enough
                    eoi = data.rfind(b"\xff\xd9", 0, start + 2)
                    if eoi != -1:
                        cand = eoi + 2
                        if 0 <= start - cand <= 256 and cand + 8 <= n and data[cand + 4:cand + 8] == b"ftyp":
                            return cand
                    return start

        idx = tail.rfind(b"ftyp", 0, idx)
    return None

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


def _copy_all_metadata_with_exiftool(src_jpg: Path, dst_jpg: Path) -> None:
    """
    Preserve EXIF/MakerNote/etc. Some phone albums rely on vendor tags to recognize Motion Photos.
    If exiftool is unavailable, do nothing.
    """
    if not shutil.which("exiftool"):
        return
    try:
        subprocess.run(
            [
                "exiftool",
                "-overwrite_original",
                "-TagsFromFile",
                str(src_jpg),
                "-all:all",
                "-unsafe",
                str(dst_jpg),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception:
        # Do not fail the pipeline if metadata copy fails; motion photo may still work on some devices.
        return
def _get_video_wh(video_path: Path) -> Optional[tuple[int, int]]:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None
    try:
        r = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                str(video_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        s = r.stdout.strip()
        if "x" in s:
            w, h = s.split("x", 1)
            return int(w), int(h)
    except Exception:
        return None
    return None
def _apply_watermark_to_video(
    video_path: Path,
    overlay_path: Path,
    output_path: Path,
    content_box: tuple[int, int, int, int],
    overlay_size: tuple[int, int],
) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to process motion photo video but was not found in PATH")

    # Still/watermark canvas (same as watermarked JPG / overlay PNG)
    canvas_w, canvas_h = overlay_size
    if canvas_w <= 0 or canvas_h <= 0:
        raise ValueError("Invalid overlay size")

    left, top, right, bottom = content_box
    content_w = right - left
    content_h = bottom - top
    if content_w <= 0 or content_h <= 0:
        raise ValueError("Invalid content box")

    # Video coded size (before rotation metadata)
    wh = _get_video_wh(video_path)
    if not wh:
        raise RuntimeError("ffprobe is required to read video width/height for motion photo overlay")
    vw, vh = wh

    rotation = _get_video_rotation(video_path)  # e.g. 270

    # Bake rotation into pixels so output is upright and we don't depend on rotate/displaymatrix quirks.
    rot_filter = ""
    disp_w, disp_h = vw, vh
    if rotation == 90:
        rot_filter = ",transpose=1"      # clockwise 90
        disp_w, disp_h = vh, vw
    elif rotation == 270:
        rot_filter = ",transpose=2"      # counter-clockwise 90
        disp_w, disp_h = vh, vw
    elif rotation == 180:
        rot_filter = ",hflip,vflip"
        disp_w, disp_h = vw, vh

    # Compute output canvas size so that border ratio matches watermarked still:
    # content area in video stays ~disp_w x disp_h, but overall canvas grows by (canvas/content) ratio.
    out_canvas_w = int(round(disp_w * (canvas_w / content_w)))
    out_canvas_h = int(round(disp_h * (canvas_h / content_h)))

    # Positions scaled to the new output canvas
    scale_x = out_canvas_w / canvas_w
    scale_y = out_canvas_h / canvas_h
    out_left = int(round(left * scale_x))
    out_top = int(round(top * scale_y))

    # Make dims even for yuv420p
    def even(x: int) -> int:
        return x if x % 2 == 0 else x - 1 if x > 1 else x

    out_canvas_w = even(out_canvas_w)
    out_canvas_h = even(out_canvas_h)
    out_left = even(out_left)
    out_top = even(out_top)

    # Also ensure content display dims are even
    disp_w = even(disp_w)
    disp_h = even(disp_h)

    # Filter:
    # 1) noautorotate + bake rotation into pixels
    # 2) scale to display size (content area)
    # 3) pad to output canvas at the scaled left/top
    # 4) scale overlay full-canvas PNG to output canvas and overlay
    filter_complex = (
        f"[0:v]setsar=1{rot_filter},"
        f"scale={disp_w}:{disp_h},"
        f"crop=trunc(iw/2)*2:trunc(ih/2)*2"
        f"[vid];"
        f"[vid]pad={out_canvas_w}:{out_canvas_h}:{out_left}:{out_top}:black[base];"
        f"[1:v]format=rgba,scale={out_canvas_w}:{out_canvas_h}[wm];"
        f"[base][wm]overlay=0:0:shortest=1[out]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-noautorotate",
        "-i", str(video_path),
        "-loop", "1",
        "-i", str(overlay_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-metadata:s:v:0", "rotate=0",   # baked rotation -> no metadata rotation
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to overlay watermark onto motion video: {exc.stderr.decode(errors='ignore')}"
        ) from exc

def _get_video_rotation(video_path: Path) -> Optional[int]:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None

    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream_tags=rotate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output = result.stdout.decode().strip()
        if output:
            return int(output)
    except Exception:
        return None
    return None
