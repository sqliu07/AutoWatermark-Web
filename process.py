import os
from pathlib import Path

import sys
import piexif
from PIL import Image
from io import BytesIO


from exif_utils import find_logo, get_manufacturer, get_exif_data, get_camera_model
from image_utils import *
from constants import CommonConstants, ImageConstants
from errors import (
    WatermarkError,
    MissingExifDataError,
    UnsupportedManufacturerError,
    ExifProcessingError,
    UnexpectedProcessingError,
    ImageTooLargeError,
)

from ultrahdr_utils import (
    split_ultrahdr,
    inject_xmp,
    update_primary_xmp_lengths,
    expand_gainmap_for_borders,
)
from motion_photo_utils import prepare_motion_photo
from logging_utils import get_logger
from services.watermark_styles import get_style, load_cached_watermark_styles


logger = get_logger("autowatermark.process")

def get_message(key, lang='zh'):
    return CommonConstants.ERROR_MESSAGES.get(key, {}).get(lang)

def _enforce_image_pixel_limit(image):
    max_pixels = ImageConstants.MAX_IMAGE_PIXELS
    image_size = image.width * image.height
    logger.info("Image size: %dx%d=%d, max allowed pixels: %s", image.width, image.height, image_size, str(max_pixels) if max_pixels else "unlimited")
    if max_pixels and image_size >= max_pixels:
        detail = f"{image.width}x{image.height}"
        raise ImageTooLargeError(detail=detail)

def _report_progress(progress_callback, progress, stage=None):
    if progress_callback:
        progress_callback(progress, stage)

def process_image(
    image_path,
    lang='zh',
    watermark_type=1,
    image_quality=95,
    notify=False,
    preview=False,
    logo_preference="xiaomi",
    progress_callback=None,
    style_config=None,
):
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
        bool or Image: True if successful, or the image object if preview is True.
    """
    try:
        if style_config is None:
            style_config = load_cached_watermark_styles(CommonConstants.WATERMARK_STYLE_CONFIG_PATH)
        style = get_style(style_config, watermark_type)
        if not style or not style["enabled"]:
            raise UnexpectedProcessingError(detail=f"Invalid watermark style: {watermark_type}")

        original_name, extension = os.path.splitext(image_path)
        output_path = f"{original_name}_watermark{extension}"

        motion_session = prepare_motion_photo(image_path)
        working_image_path = image_path
        if motion_session and motion_session.has_motion:
            working_image_path = str(motion_session.still_path)
        else:
            motion_session = None

        progress_step = 0
        progress_total = 5
        def advance_progress(stage):
            nonlocal progress_step
            progress_step += 1
            _report_progress(progress_callback, min(progress_step / progress_total, 1.0), stage)

        logger.info("Received image: %s, output: %s, is_motion: %s, start processing...", image_path, output_path, None!=motion_session)

        # --- Ultra HDR detect & split (JPEG_R) ---
        ultrahdr_parts = None
        try:
            data_bytes = Path(working_image_path).read_bytes()
            ultrahdr_parts = split_ultrahdr(data_bytes)
        except Exception:
            ultrahdr_parts = None

        if ultrahdr_parts is not None:
            image = Image.open(BytesIO(ultrahdr_parts.primary_jpeg))
        else:
            image = Image.open(working_image_path)

        image = reset_image_orientation(image)
        _enforce_image_pixel_limit(image)
        advance_progress("loaded")

        exif_bytes = image.info.get('exif')
        exif_dict = None
        if exif_bytes:
            try:
                exif_dict = piexif.load(exif_bytes)
            except Exception:
                exif_bytes = b''
        else:
            exif_bytes = b''

        if exif_dict is None:
            raise MissingExifDataError()

        manufacturer = get_manufacturer(working_image_path, exif_dict)
        if not manufacturer:
            raise MissingExifDataError()

        camera_model = get_camera_model(exif_dict)

        logo_path = None
        if manufacturer and "xiaomi" in manufacturer.lower():
            if logo_preference == "leica":
                logo_path = find_logo("leica")
            else:
                logo_path = find_logo(manufacturer)
        else:
            logo_path = find_logo(manufacturer)
        if logo_path is None:
            detail = manufacturer if not camera_model else f"{manufacturer} {camera_model}"
            raise UnsupportedManufacturerError(manufacturer, detail=detail)

        result = get_exif_data(working_image_path, exif_dict)
        if result is None or result == (None, None):
             raise ExifProcessingError()

        camera_info, shooting_info = result
        advance_progress("metadata")


        camera_info_lines = camera_info.split('\n')
        shooting_info_lines = shooting_info.split('\n')
        logger.info("Received image, camera_info: %s %s, shooting_info: %s", camera_info_lines[0], camera_info_lines[1], shooting_info_lines[0])


        needs_metadata = (motion_session is not None) or (ultrahdr_parts is not None)
        logger.info("Generating watermark, current manufacturer: %s", manufacturer)
        generated = generate_watermark_image(
            image,
            logo_path,
            camera_info_lines,
            shooting_info_lines,
            CommonConstants.GLOBAL_FONT_PATH_LIGHT,
            CommonConstants.GLOBAL_FONT_PATH_BOLD,
            watermark_type,
            return_metadata=needs_metadata,
            style_config=style_config,
            style=style,
        )
        logger.info("Finished generating watermark for %s", image_path)
        advance_progress("rendered")

        if needs_metadata:
            new_image, watermark_metadata = generated
        else:
            new_image = generated
            watermark_metadata = None

        if preview:
            return new_image
        else:
            advance_progress("saving")
            if motion_session and watermark_metadata and style["supports_motion"]:
                temp_output = Path(motion_session.still_path.parent) / "watermarked_motion_frame.jpg"
                new_image.save(temp_output, exif=exif_bytes, quality=image_quality)
                motion_session.finalize(temp_output, Path(output_path), watermark_metadata)
            else:
                if ultrahdr_parts is not None:
                    if not style["supports_ultrahdr"]:
                        logger.warning(
                            "watermark style %s does not support Ultra HDR preservation; fallback to SDR output.",
                            watermark_type,
                        )
                        new_image.save(output_path, exif=exif_bytes, quality=image_quality)
                        advance_progress("saved")
                        return True

                    # 1) encode new primary JPEG bytes (no XMP yet)
                    buf = BytesIO()
                    save_kwargs = dict(format="JPEG", quality=image_quality, exif=exif_bytes)
                    icc_profile = image.info.get("icc_profile")
                    if icc_profile:
                        save_kwargs["icc_profile"] = icc_profile
                    new_image.save(buf, **save_kwargs)
                    new_primary_jpeg = buf.getvalue()

                    # 2) expand/pad gainmap if size changed
                    gainmap_jpeg = ultrahdr_parts.gainmap_jpeg
                    if (ultrahdr_parts.gainmap_xmp is not None
                            and watermark_metadata is not None
                            and tuple(image.size) != tuple(new_image.size)):
                        gainmap_jpeg = expand_gainmap_for_borders(
                            orig_gainmap_jpeg=ultrahdr_parts.gainmap_jpeg,
                            orig_gainmap_xmp=ultrahdr_parts.gainmap_xmp,
                            orig_primary_size=image.size,
                            new_primary_size=new_image.size,
                            content_box=watermark_metadata["content_box"],
                        )

                    # 3) update primary XMP lengths and inject
                    if ultrahdr_parts.primary_xmp is None:
                        raise UnexpectedProcessingError(detail="Primary XMP missing; cannot rebuild Ultra HDR container.")

                    tmp_primary = inject_xmp(new_primary_jpeg, ultrahdr_parts.primary_xmp)
                    updated_xmp = update_primary_xmp_lengths(
                        ultrahdr_parts.primary_xmp,
                        primary_len=len(tmp_primary),
                        gainmap_len=len(gainmap_jpeg),
                    )
                    final_primary = inject_xmp(new_primary_jpeg, updated_xmp)

                    Path(output_path).write_bytes(final_primary + gainmap_jpeg)
                    advance_progress("saved")
                    return True

                # --- original path (SDR) ---
                if motion_session and watermark_metadata and style["supports_motion"]:
                    temp_output = Path(motion_session.still_path.parent) / "watermarked_motion_frame.jpg"
                    new_image.save(temp_output, exif=exif_bytes, quality=image_quality)
                    motion_session.finalize(temp_output, Path(output_path), watermark_metadata)
                else:
                    new_image.save(output_path, exif=exif_bytes, quality=image_quality)
                advance_progress("saved")
                return True
            # comment this, no need notify.
            # if notify:
            #     url = "ntfy_url"
            #     title = "This is your image with watermark."
            #     priority = "high"
            #     command = f'curl -H "Title: {title}" -H"Priority: {priority}" -T {output_path} {url}'
            #     os.system(command)
            return True
    except WatermarkError:
        raise
    except Exception as exc:
        raise UnexpectedProcessingError(detail=str(exc)) from exc
    finally:
        if 'motion_session' in locals() and motion_session is not None:
            motion_session.cleanup()

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
