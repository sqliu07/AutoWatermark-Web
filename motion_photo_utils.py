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
    rb"(?:GCamera:MicroVideoOffset|GCamera:MotionPhotoOffset|Camera:MotionPhotoOffset)=\"(\d+)\""
)
MICRO_VIDEO_LENGTH_PATTERN = re.compile(
    rb"(?:GCamera:MicroVideoLength|GCamera:MotionPhotoLength|Camera:MotionPhotoLength)=\"(\d+)\""
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
        )
        watermarked_video_bytes = watermarked_video_path.read_bytes()

        jpeg_with_xmp = _inject_xmp(
            Path(watermarked_path).read_bytes(),
            _prepare_xmp(self.xmp_bytes, len(watermarked_video_bytes))
        )

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
    if length and length > 0:
        video_length = length
        video_start = file_size - video_length
    elif offset and offset > 0:
        video_start = file_size - offset
        video_length = offset
    else:
        return _RawMotionComponents(photo_bytes=data, video_bytes=b"", xmp_bytes=xmp)

    if video_start <= 0 or video_start >= file_size:
        return _RawMotionComponents(photo_bytes=data, video_bytes=b"", xmp_bytes=xmp)

    photo_bytes = data[:video_start]
    video_bytes = data[video_start:video_start + video_length]
    return _RawMotionComponents(photo_bytes=photo_bytes, video_bytes=video_bytes, xmp_bytes=xmp)


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


def _prepare_xmp(xmp_bytes: bytes, video_length: int) -> bytes:
    xmp_text = xmp_bytes.decode("utf-8", errors="ignore")

    for attr in OFFSET_ATTRS:
        xmp_text = _update_attribute_if_exists(xmp_text, attr, str(video_length))

    for attr in LENGTH_ATTRS:
        xmp_text = _update_attribute_if_exists(xmp_text, attr, str(video_length))

    return xmp_text.encode("utf-8")


def _update_attribute_if_exists(xmp_text: str, attr: str, value: str) -> str:
    pattern = re.compile(rf"({re.escape(attr)}=\")([^\"]+)(\")")
    if pattern.search(xmp_text):
        return pattern.sub(rf"\g<1>{value}\g<3>", xmp_text)
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


def _apply_watermark_to_video(
    video_path: Path,
    overlay_path: Path,
    output_path: Path,
    content_box: tuple[int, int, int, int],
) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to process motion photo video but was not found in PATH")

    left, top, right, bottom = content_box
    content_width = right - left
    content_height = bottom - top
    if content_width <= 0 or content_height <= 0:
        raise ValueError("Invalid content box for motion photo overlay")

    rotation = _get_video_rotation(video_path)

    filter_complex = (
        f"[0:v]scale={content_width}:{content_height}:force_original_aspect_ratio=decrease,"
        f"pad={content_width}:{content_height}:(ow-iw)/2:(oh-ih)/2,setsar=1[vscaled];"
        f"[1:v]format=rgba[overlay];"
        f"[overlay][vscaled]overlay={left}:{top}:shortest=1[out]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-loop",
        "1",
        "-i",
        str(overlay_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
    ]

    if rotation is not None:
        command.extend(["-metadata:s:v:0", f"rotate={rotation}"])

    command.append(str(output_path))

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
