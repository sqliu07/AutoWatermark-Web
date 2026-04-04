"""Motion Photo 格式处理核心。"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "_RawMotionComponents",
    "MotionPhotoSession",
    "prepare_motion_photo",
    "_split_motion_photo",
    "_mp4_looks_valid",
    "_find_mp4_start_by_ftyp",
]

from media.xmp import (
    MICRO_VIDEO_LENGTH_PATTERN,
    MICRO_VIDEO_OFFSET_PATTERN,
    OFFSET_ATTRS,
    LENGTH_ATTRS,
    _extract_xmp_segment,
    _parse_first_match,
    _looks_like_motionphoto_flag,
    _prepare_xmp_ultrahdr_motion,
    _prepare_xmp,
    _inject_xmp,
)
from media.video import (
    _apply_watermark_to_video,
    _copy_all_metadata_with_exiftool,
)


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

    # --- Ultra HDR cover support (optional) ---
    ultrahdr_gainmap_jpeg: Optional[bytes] = None
    ultrahdr_gainmap_xmp: Optional[bytes] = None
    ultrahdr_primary_size: Optional[tuple[int, int]] = None
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
        watermarked_still_bytes = Path(watermarked_path).read_bytes()

        # --- Ultra HDR cover path: output = primary(with XMP) + gainmap + video ---
        if self.ultrahdr_gainmap_jpeg:
            gainmap_jpeg = self.ultrahdr_gainmap_jpeg

            # If watermarking changed canvas size (your type 1/2/3 often adds borders),
            # expand gainmap with neutral pixels so border area has gain=1 (no HDR boost).
            try:
                from media.ultrahdr import expand_gainmap_for_borders
                from io import BytesIO
                from PIL import Image

                if self.ultrahdr_gainmap_xmp is not None:
                    new_im = Image.open(BytesIO(watermarked_still_bytes))
                    try:
                        new_im.load()
                        new_size = new_im.size
                    finally:
                        new_im.close()

                    orig_size = self.ultrahdr_primary_size
                    if orig_size is None:
                        src_im = Image.open(self.still_path)
                        try:
                            src_im.load()
                            orig_size = src_im.size
                        finally:
                            src_im.close()

                    if orig_size and tuple(orig_size) != tuple(new_size):
                        gainmap_jpeg = expand_gainmap_for_borders(
                            orig_gainmap_jpeg=self.ultrahdr_gainmap_jpeg,
                            orig_gainmap_xmp=self.ultrahdr_gainmap_xmp,
                            orig_primary_size=orig_size,
                            new_primary_size=new_size,
                            content_box=content_box,
                        )
            except Exception:
                # If anything fails, keep original gainmap as-is (HDR may still work but border can look odd)
                pass

            # Two-pass: primary length depends on injected XMP size
            xmp0 = _prepare_xmp_ultrahdr_motion(
                self.xmp_bytes,
                primary_length=0,
                gainmap_length=len(gainmap_jpeg),
                video_length=len(watermarked_video_bytes),
            )
            tmp_primary = _inject_xmp(watermarked_still_bytes, xmp0)

            xmp1 = _prepare_xmp_ultrahdr_motion(
                self.xmp_bytes,
                primary_length=len(tmp_primary),
                gainmap_length=len(gainmap_jpeg),
                video_length=len(watermarked_video_bytes),
            )
            final_primary = _inject_xmp(watermarked_still_bytes, xmp1)

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(final_primary + gainmap_jpeg + watermarked_video_bytes)
            return

        # --- Original SDR motion photo path ---
        jpeg_with_xmp = _inject_xmp(
            watermarked_still_bytes,
            _prepare_xmp(self.xmp_bytes, len(watermarked_video_bytes)),
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
    still_bytes = components.photo_bytes
    ultrahdr_gainmap_jpeg = None
    ultrahdr_gainmap_xmp = None
    ultrahdr_primary_size = None

    # --- Try detect Ultra HDR (JPEG_R) in the still part ---
    # 如果 photo_bytes 是 JPEG_R（primary+gainmap），则：
    # 1) still_path 写 primary_jpeg
    # 2) session 缓存 gainmap_jpeg/xmp，finalize 时再封装回去
    try:
        from media.ultrahdr import split_ultrahdr
        from io import BytesIO
        from PIL import Image

        parts = split_ultrahdr(components.photo_bytes)
        if parts.gainmap_jpeg:
            still_bytes = parts.primary_jpeg
            ultrahdr_gainmap_jpeg = parts.gainmap_jpeg
            ultrahdr_gainmap_xmp = parts.gainmap_xmp
            try:
                im = Image.open(BytesIO(parts.primary_jpeg))
                try:
                    im.load()
                    ultrahdr_primary_size = im.size
                finally:
                    im.close()
            except Exception:
                ultrahdr_primary_size = None
    except Exception:
        pass

    still_path = Path(workspace.name) / f"{path.stem}_motion_still.jpg"
    still_path.write_bytes(still_bytes)

    return MotionPhotoSession(
        still_path=still_path,
        video_bytes=components.video_bytes,
        xmp_bytes=components.xmp_bytes,
        _workspace=workspace,
        ultrahdr_gainmap_jpeg=ultrahdr_gainmap_jpeg,
        ultrahdr_gainmap_xmp=ultrahdr_gainmap_xmp,
        ultrahdr_primary_size=ultrahdr_primary_size,
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
