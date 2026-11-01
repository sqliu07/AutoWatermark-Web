"""ffmpeg / ffprobe / exiftool 视频处理工具。"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from imaging.safety import MAX_RASTER_PIXELS, validate_input_size, validate_raster_size

MAX_VIDEO_SECONDS = 30
MAX_VIDEO_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_PROBE_JSON_CHARS = 64 * 1024

# Only decode self-contained phone videos. In particular, do not auto-detect
# playlists, follow network protocols, or resolve QuickTime external tracks.
_MOTION_INPUT_OPTIONS = (
    "-f", "mov",
    "-protocol_whitelist", "file",
    "-enable_drefs", "0",
    "-use_absolute_path", "0",
    "-max_streams", "8",
    "-max_pixels", str(MAX_RASTER_PIXELS),
    "-threads", "2",
)

__all__ = [
    "_copy_all_metadata_with_exiftool",
    "_get_video_wh",
    "_normalize_rotation",
    "_apply_watermark_to_video",
    "_get_video_rotation",
]


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
            timeout=30,
        )
    except Exception:
        # Do not fail the pipeline if metadata copy fails; motion photo may still work on some devices.
        return

@dataclass(frozen=True)
class _VideoMetadata:
    width: int
    height: int
    duration: float
    rotation: Optional[int]


def _read_video_metadata(video_path: Path) -> tuple[dict, dict]:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        raise RuntimeError("ffprobe is required to read motion photo metadata but was not found in PATH")
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                *_MOTION_INPUT_OPTIONS,
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration",
                "-of", "json",
                str(video_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown ffprobe error").strip()
        raise RuntimeError(f"ffprobe failed to read motion photo metadata: {detail[:2000]}") from exc

    if not isinstance(result.stdout, str) or len(result.stdout) > MAX_PROBE_JSON_CHARS:
        raise ValueError("Motion photo metadata exceeded the size limit")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Invalid motion photo metadata")
    streams = payload.get("streams")
    file_format = payload.get("format", {})
    if (not isinstance(streams, list) or len(streams) != 1
            or not isinstance(streams[0], dict) or not isinstance(file_format, dict)):
        raise ValueError("Invalid motion photo video stream metadata")
    return streams[0], file_format


def _video_dimensions(stream: dict) -> tuple[int, int]:
    width, height = stream.get("width"), stream.get("height")
    if (not isinstance(width, int) or isinstance(width, bool)
            or not isinstance(height, int) or isinstance(height, bool)):
        raise ValueError("Invalid motion photo video dimensions")
    size = width, height
    validate_input_size(size)
    return size


def _video_duration(file_format: dict) -> float:
    value = file_format.get("duration")
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Invalid motion photo video duration")
    duration = float(value)
    if not math.isfinite(duration) or not 0 < duration <= MAX_VIDEO_SECONDS:
        raise ValueError(f"Motion photo video must be between 0 and {MAX_VIDEO_SECONDS} seconds")
    return duration


def _video_rotation(stream: dict) -> Optional[int]:
    side_data_list = stream.get("side_data_list", [])
    tags = stream.get("tags", {})
    if not isinstance(side_data_list, list) or not isinstance(tags, dict):
        raise ValueError("Invalid motion photo rotation metadata")
    for side_data in side_data_list:
        if not isinstance(side_data, dict):
            raise ValueError("Invalid motion photo rotation metadata")
        rotation = side_data.get("rotation")
        if rotation is not None:
            return _normalize_rotation(rotation)
    rotate_tag = tags.get("rotate")
    if rotate_tag is not None:
        # Legacy tags have the opposite sign from display-matrix side data.
        return (-_normalize_rotation(rotate_tag)) % 360
    return None


def _probe_video(video_path: Path) -> _VideoMetadata:
    stream, file_format = _read_video_metadata(video_path)
    width, height = _video_dimensions(stream)
    return _VideoMetadata(width, height, _video_duration(file_format), _video_rotation(stream))


def _get_video_wh(video_path: Path) -> tuple[int, int]:
    stream, _ = _read_video_metadata(video_path)
    return _video_dimensions(stream)


def _get_video_duration(video_path: Path) -> float:
    _, file_format = _read_video_metadata(video_path)
    return _video_duration(file_format)


def _normalize_rotation(value: int | float | str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Invalid motion photo video rotation")
    rotation = float(value)
    if not math.isfinite(rotation):
        raise ValueError("Invalid motion photo video rotation")
    return int(round(rotation)) % 360

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
    validate_raster_size(overlay_size)

    left, top, right, bottom = content_box
    content_w = right - left
    content_h = bottom - top
    if not (0 <= left < right <= canvas_w and 0 <= top < bottom <= canvas_h):
        raise ValueError("Invalid content box")

    # Video coded size (before rotation metadata)
    metadata = _probe_video(video_path)
    vw, vh = metadata.width, metadata.height
    rotation = metadata.rotation  # e.g. 270

    # Bake rotation into pixels so output is upright and we don't depend on rotate/displaymatrix quirks.
    rot_filter = ""
    disp_w, disp_h = vw, vh
    if rotation == 90:
        rot_filter = ",transpose=2"      # counter-clockwise 90
        disp_w, disp_h = vh, vw
    elif rotation == 270:
        rot_filter = ",transpose=1"      # clockwise 90
        disp_w, disp_h = vh, vw
    elif rotation == 180:
        rot_filter = ",hflip,vflip"
        disp_w, disp_h = vw, vh

    # Compute output canvas size so that border ratio matches watermarked still:
    # content area in video stays ~disp_w x disp_h, but overall canvas grows by (canvas/content) ratio.
    out_canvas_w = int(round(disp_w * (canvas_w / content_w)))
    out_canvas_h = int(round(disp_h * (canvas_h / content_h)))
    validate_input_size((out_canvas_w, out_canvas_h))

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
        "-nostdin",
        "-v", "error",
        "-xerror",
        "-filter_complex_threads", "2",
        "-noautorotate",
        *_MOTION_INPUT_OPTIONS,
        "-i", str(video_path),
        "-f", "image2",
        "-pattern_type", "none",
        "-protocol_whitelist", "file",
        "-c:v", "png",
        "-threads", "2",
        "-max_pixels", str(MAX_RASTER_PIXELS),
        "-loop", "1",
        "-i", str(overlay_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-threads", "2",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-t", str(MAX_VIDEO_SECONDS),
        "-fpsmax", "120",
        "-frames:v", "3600",
        "-fs", str(MAX_VIDEO_OUTPUT_BYTES),
        "-metadata:s:v:0", "rotate=0",   # baked rotation -> no metadata rotation
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if output_path.stat().st_size >= MAX_VIDEO_OUTPUT_BYTES:
            raise ValueError("Motion photo video output exceeded the size limit")
    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to overlay watermark onto motion video: {exc.stderr.decode(errors='ignore')}"
        ) from exc
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

def _get_video_rotation(video_path: Path) -> Optional[int]:
    try:
        stream, _ = _read_video_metadata(video_path)
        return _video_rotation(stream)
    except Exception:
        return None
    return None
