import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

import sys
import piexif
from PIL import Image
from io import BytesIO


from exif import find_logo, get_manufacturer, get_exif_data, get_exif_data_with_exiftool, get_camera_model
from imaging import reset_image_orientation, generate_watermark_image
from constants import CommonConstants, ImageConstants
from errors import (
    WatermarkError,
    MissingExifDataError,
    UnsupportedManufacturerError,
    ExifProcessingError,
    UnexpectedProcessingError,
    ImageTooLargeError,
)

from media.ultrahdr import (
    split_ultrahdr,
    inject_xmp,
    update_primary_xmp_lengths,
    build_primary_xmp_for_gainmap,
    expand_gainmap_for_borders,
)
from media.motion_photo import prepare_motion_photo
from process_result import ProcessResult
from logging_utils import get_logger
from services.i18n import get_error_message as get_message
from services.watermark_styles import get_style, load_cached_watermark_styles


logger = get_logger("autowatermark.process")

def _enforce_image_pixel_limit(image: Image.Image) -> None:
    max_pixels = ImageConstants.MAX_IMAGE_PIXELS
    image_size = image.width * image.height
    logger.info("Image size: %dx%d=%d, max allowed pixels: %s", image.width, image.height, image_size, str(max_pixels) if max_pixels else "unlimited")
    if max_pixels and image_size > max_pixels:
        detail = f"{image.width}x{image.height}"
        raise ImageTooLargeError(detail=detail)

def _report_progress(progress_callback: Optional[Callable], progress: float, stage: Optional[str] = None) -> None:
    if progress_callback:
        progress_callback(progress, stage)


@dataclass
class _ProcessingState:
    """process_image() 的中间处理状态。"""
    image_path: str
    output_path: str
    working_image_path: str
    style_config: dict
    style: dict
    watermark_type: int
    image_quality: int
    logo_preference: str
    motion_session: object = None
    ultrahdr_parts: object = None
    image: object = None       # PIL Image
    exif_bytes: bytes = b''
    exif_dict: dict = None
    fallback_metadata: dict = None
    using_fallback_metadata: bool = False
    manufacturer: str = None
    camera_model: str = None
    logo_path: str = None
    camera_info: str = None
    shooting_info: str = None
    new_image: object = None   # PIL Image
    watermark_metadata: dict = None


def _detect_format(state: _ProcessingState) -> None:
    """检测 motion photo 和 Ultra HDR 格式，更新 working_image_path。"""
    state.motion_session = prepare_motion_photo(state.image_path)
    if state.motion_session and state.motion_session.has_motion:
        state.working_image_path = str(state.motion_session.still_path)
    else:
        state.motion_session = None

    try:
        data_bytes = Path(state.working_image_path).read_bytes()
        state.ultrahdr_parts = split_ultrahdr(data_bytes)
    except Exception:
        state.ultrahdr_parts = None

    if state.ultrahdr_parts is not None and (
        state.ultrahdr_parts.primary_xmp is None or state.ultrahdr_parts.gainmap_xmp is None
    ):
        if state.ultrahdr_parts.primary_xmp is None and state.ultrahdr_parts.gainmap_xmp is not None:
            state.ultrahdr_parts.primary_xmp = build_primary_xmp_for_gainmap(
                len(state.ultrahdr_parts.gainmap_jpeg)
            )
        else:
            logger.warning(
                "Incomplete Ultra HDR metadata for %s; fallback to SDR output.",
                state.working_image_path,
            )
            state.ultrahdr_parts = None


def _load_image(state: _ProcessingState) -> None:
    """从文件或 Ultra HDR 主图打开图像，重置方向，检查像素上限。"""
    if state.ultrahdr_parts is not None:
        state.image = Image.open(BytesIO(state.ultrahdr_parts.primary_jpeg))
    else:
        state.image = Image.open(state.working_image_path)
    state.image = reset_image_orientation(state.image)
    _enforce_image_pixel_limit(state.image)


def _extract_metadata(state: _ProcessingState) -> None:
    """提取 EXIF 数据、制造商、相机型号、拍摄信息。"""
    state.exif_bytes = state.image.info.get('exif')
    state.exif_dict = None
    state.fallback_metadata = None
    if state.exif_bytes:
        try:
            state.exif_dict = piexif.load(state.exif_bytes)
        except Exception:
            state.exif_bytes = b''
    else:
        state.exif_bytes = b''

    if state.exif_dict is None:
        state.fallback_metadata = get_exif_data_with_exiftool(state.working_image_path)
        if not state.fallback_metadata:
            raise MissingExifDataError()

    state.using_fallback_metadata = state.exif_dict is None
    state.manufacturer = get_manufacturer(state.working_image_path, state.exif_dict)
    if not state.manufacturer:
        state.fallback_metadata = state.fallback_metadata or get_exif_data_with_exiftool(state.working_image_path)
        state.manufacturer = state.fallback_metadata.get("manufacturer") if state.fallback_metadata else None
        if not state.manufacturer:
            raise MissingExifDataError()
        state.using_fallback_metadata = True

    state.camera_model = get_camera_model(state.exif_dict) if state.exif_dict is not None else None
    if not state.camera_model and state.fallback_metadata:
        state.camera_model = state.fallback_metadata.get("camera_model")

    result = None if state.using_fallback_metadata else get_exif_data(state.working_image_path, state.exif_dict)
    if (result is None or result == (None, None)) and state.fallback_metadata:
        result = (
            state.fallback_metadata.get("camera_info"),
            state.fallback_metadata.get("shooting_info"),
        )
    if result is None or result == (None, None):
        raise ExifProcessingError()

    state.camera_info, state.shooting_info = result


def _resolve_logo(state: _ProcessingState) -> None:
    """根据制造商和样式配置查找品牌 logo。"""
    if state.manufacturer and "xiaomi" in state.manufacturer.lower():
        if state.logo_preference == "leica":
            state.logo_path = find_logo("leica")
        else:
            state.logo_path = find_logo(state.manufacturer)
    else:
        state.logo_path = find_logo(state.manufacturer)
    if state.logo_path is None:
        detail = state.manufacturer if not state.camera_model else f"{state.manufacturer} {state.camera_model}"
        raise UnsupportedManufacturerError(state.manufacturer, detail=detail)


def _render_watermark(state: _ProcessingState) -> None:
    """生成水印图像，写入 state.new_image 和 state.watermark_metadata。"""
    camera_info_lines = state.camera_info.split('\n')
    shooting_info_lines = state.shooting_info.split('\n')
    logger.info(
        "Received image, camera_info: %s %s, shooting_info: %s",
        camera_info_lines[0], camera_info_lines[1], shooting_info_lines[0],
    )

    needs_metadata = (state.motion_session is not None) or (state.ultrahdr_parts is not None)
    logger.info("Generating watermark, current manufacturer: %s", state.manufacturer)
    generated = generate_watermark_image(
        state.image,
        state.logo_path,
        camera_info_lines,
        shooting_info_lines,
        CommonConstants.GLOBAL_FONT_PATH_LIGHT,
        CommonConstants.GLOBAL_FONT_PATH_BOLD,
        state.watermark_type,
        font_path_regular=CommonConstants.GLOBAL_FONT_PATH_MONO,
        font_path_symbol=CommonConstants.GLOBAL_FONT_PATH_REGULAR,
        return_metadata=needs_metadata,
        style_config=state.style_config,
        style=state.style,
    )
    logger.info("Finished generating watermark for %s", state.image_path)

    if needs_metadata:
        state.new_image, state.watermark_metadata = generated
    else:
        state.new_image = generated
        state.watermark_metadata = None


def _save_output(state: _ProcessingState, preview: bool, advance_progress: Callable) -> ProcessResult:
    """保存输出图像（预览 / motion photo / Ultra HDR / 标准 JPEG）。"""
    if preview:
        return ProcessResult(preview_image=state.new_image)

    advance_progress("saving")
    is_motion = False
    if state.motion_session and state.watermark_metadata and state.style["supports_motion"]:
        is_motion = True
        temp_output = Path(state.motion_session.still_path.parent) / "watermarked_motion_frame.jpg"
        state.new_image.save(temp_output, exif=state.exif_bytes, quality=state.image_quality)
        state.motion_session.finalize(temp_output, Path(state.output_path), state.watermark_metadata)
    else:
        if state.ultrahdr_parts is not None:
            if not state.style["supports_ultrahdr"]:
                logger.warning(
                    "watermark style %s does not support Ultra HDR preservation; fallback to SDR output.",
                    state.watermark_type,
                )
                state.new_image.save(state.output_path, exif=state.exif_bytes, quality=state.image_quality)
                advance_progress("saved")
                return ProcessResult()

            # 1) 编码新的主图 JPEG（暂不含 XMP）
            buf = BytesIO()
            save_kwargs = dict(format="JPEG", quality=state.image_quality, exif=state.exif_bytes)
            icc_profile = state.image.info.get("icc_profile")
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile
            state.new_image.save(buf, **save_kwargs)
            new_primary_jpeg = buf.getvalue()

            # 2) 尺寸变化时扩展 gainmap
            gainmap_jpeg = state.ultrahdr_parts.gainmap_jpeg
            if (state.ultrahdr_parts.gainmap_xmp is not None
                    and state.watermark_metadata is not None
                    and tuple(state.image.size) != tuple(state.new_image.size)):
                gainmap_jpeg = expand_gainmap_for_borders(
                    orig_gainmap_jpeg=state.ultrahdr_parts.gainmap_jpeg,
                    orig_gainmap_xmp=state.ultrahdr_parts.gainmap_xmp,
                    orig_primary_size=state.image.size,
                    new_primary_size=state.new_image.size,
                    content_box=state.watermark_metadata["content_box"],
                )

            # 3) 更新主图 XMP 长度并注入
            if state.ultrahdr_parts.primary_xmp is None:
                raise UnexpectedProcessingError(detail="Primary XMP missing; cannot rebuild Ultra HDR container.")

            tmp_primary = inject_xmp(new_primary_jpeg, state.ultrahdr_parts.primary_xmp)
            updated_xmp = update_primary_xmp_lengths(
                state.ultrahdr_parts.primary_xmp,
                primary_len=len(tmp_primary),
                gainmap_len=len(gainmap_jpeg),
            )
            final_primary = inject_xmp(new_primary_jpeg, updated_xmp)

            Path(state.output_path).write_bytes(final_primary + gainmap_jpeg)
            advance_progress("saved")
            return ProcessResult()

        state.new_image.save(state.output_path, exif=state.exif_bytes, quality=state.image_quality)
        advance_progress("saved")
        return ProcessResult()
    return ProcessResult(is_motion=is_motion)


def _cleanup(state: Optional[_ProcessingState]) -> None:
    """释放处理过程中占用的资源。"""
    if state is None:
        return
    if state.image is not None:
        try:
            state.image.close()
        except Exception:
            pass
    if state.new_image is not None:
        try:
            state.new_image.close()
        except Exception:
            pass
    if state.motion_session is not None:
        state.motion_session.cleanup()


def process_image(
    image_path: str,
    lang: str = 'zh',
    watermark_type: int = 1,
    image_quality: int = 95,
    notify: bool = False,
    preview: bool = False,
    logo_preference: str = "xiaomi",
    progress_callback: Optional[Callable[[float, Optional[str]], None]] = None,
    style_config: Optional[dict] = None,
) -> ProcessResult:
    """
    Adds a watermark to the given image.

    Args:
        image_path (str): The path to the image file.
        lang (str, optional): The language for error messages. Defaults to 'zh'.
        watermark_type (int, optional): The type of watermark to add. Defaults to 1.
        image_quality (int, optional): The quality of the output image. Defaults to 95.
        notify (bool, optional): Whether to send a notification. Defaults to False.
        preview (bool, optional): Whether to return the image object for preview. Defaults to False.
        progress_callback (callable, optional): Callback for progress updates.
        style_config (dict, optional): Loaded watermark style config.

    Returns:
        ProcessResult: 处理结果，包含 success、is_motion、preview_image 字段。
    """
    state = None
    try:
        if style_config is None:
            style_config = load_cached_watermark_styles(CommonConstants.WATERMARK_STYLE_CONFIG_PATH)
        style = get_style(style_config, watermark_type)
        if not style or not style["enabled"]:
            raise UnexpectedProcessingError(detail=f"Invalid watermark style: {watermark_type}")

        original_name, extension = os.path.splitext(image_path)
        output_path = f"{original_name}_watermark{extension}"

        state = _ProcessingState(
            image_path=image_path,
            output_path=output_path,
            working_image_path=image_path,
            style_config=style_config,
            style=style,
            watermark_type=watermark_type,
            image_quality=image_quality,
            logo_preference=logo_preference,
        )

        progress_step = 0
        progress_total = 5
        def advance_progress(stage):
            nonlocal progress_step
            progress_step += 1
            _report_progress(progress_callback, min(progress_step / progress_total, 1.0), stage)

        _detect_format(state)
        logger.info(
            "Received image: %s, output: %s, is_motion: %s, start processing...",
            image_path, output_path, None != state.motion_session,
        )
        _load_image(state)
        advance_progress("loaded")

        _extract_metadata(state)
        if state.logo_path is None and style.get("requires_logo", True):
            _resolve_logo(state)
        advance_progress("metadata")

        _render_watermark(state)
        advance_progress("rendered")

        return _save_output(state, preview, advance_progress)

    except WatermarkError:
        raise
    except Exception as exc:
        raise UnexpectedProcessingError(detail=str(exc)) from exc
    finally:
        _cleanup(state)

def main():
    """Main function to handle command-line arguments."""
    if len(sys.argv) < 5:
        logger.error("Usage: python process.py <image_path> <lang> <watermark_type> <image_quality>")
        sys.exit(1)

    image_path = sys.argv[1]
    lang = sys.argv[2]
    try:
        watermark_type = int(sys.argv[3])
        image_quality = int(sys.argv[4])
    except ValueError:
        logger.error("Error: watermark_type and image_quality must be integers.")
        sys.exit(1)

    notify = False # Or get from args if needed
    try:
        process_image(image_path, lang, watermark_type, image_quality, notify)
    except WatermarkError as err:
        message = get_message(err.get_message_key(), lang) or err.get_detail() or err.get_message_key()
        logger.error(message)
        sys.exit(1)
    except Exception as exc:
        logger.error(str(exc))
        sys.exit(1)

if __name__ == "__main__":
    main()
