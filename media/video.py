"""ffmpeg / ffprobe / exiftool 视频处理工具。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

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

def _get_video_wh(video_path: Path) -> tuple[int, int]:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        raise RuntimeError("ffprobe is required to read motion photo video dimensions but was not found in PATH")
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
            timeout=30,
        )
        s = r.stdout.strip()
        match = re.search(r"(\d+)x(\d+)", s)
        if match:
            return int(match.group(1)), int(match.group(2))
        raise RuntimeError(f"Unable to parse video dimensions from ffprobe output: {s or '<empty>'}")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "unknown ffprobe error"
        raise RuntimeError(f"ffprobe failed to read motion photo video dimensions: {detail}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Unable to parse video dimensions from ffprobe output: {s or '<empty>'}") from exc

def _normalize_rotation(value: int | float | str) -> int:
    return int(round(float(value))) % 360

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
    vw, vh = _get_video_wh(video_path)

    rotation = _get_video_rotation(video_path)  # e.g. 270

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
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
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
                "-show_streams",
                "-of",
                "json",
                str(video_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        stream = (payload.get("streams") or [{}])[0]

        for side_data in stream.get("side_data_list") or []:
            rotation = side_data.get("rotation")
            if rotation is not None:
                return _normalize_rotation(rotation)

        rotate_tag = (stream.get("tags") or {}).get("rotate")
        if rotate_tag:
            # Legacy rotate tag uses the opposite sign convention from side_data rotation.
            return (-_normalize_rotation(rotate_tag)) % 360
    except Exception:
        return None
    return None
