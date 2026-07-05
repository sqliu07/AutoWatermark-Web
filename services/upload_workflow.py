from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from werkzeug.utils import secure_filename

from constants import ImageConstants, format_pixel_limit
from errors import WatermarkError, WatermarkErrorCode
from process import detect_image_features
from services import task_lifecycle
from services.download_token import verify_token
from services.i18n import get_error_message, normalize_lang
from services.tasks import (
    TaskPayload,
    allowed_file,
    cleanup_old_tasks,
    detect_manufacturer,
    normalize_image_quality,
    submit_existing_task,
    submit_task,
)
from services.watermark_styles import get_default_style_id, is_style_enabled


@dataclass(frozen=True)
class WorkflowResponse:
    payload: dict[str, Any]
    status_code: int


@dataclass(frozen=True)
class PreviewFile:
    status_code: int
    file_path: str | None = None
    error: str | None = None
    render_deleted: bool = False


@dataclass(frozen=True)
class MotionVideo:
    status_code: int
    file_path: str | None = None
    filename: str | None = None
    video_start: int = 0
    file_size: int = 0
    error: str | None = None


def _requested_bool(form, name: str) -> bool | None:
    value = form.get(name)
    if value is None:
        return None
    return str(value).lower() in {"1", "true", "yes", "on"}


def _json_bool(payload: dict, name: str, default: bool = True) -> bool:
    value = payload.get(name, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _has_media_options(features: dict | None) -> bool:
    return bool(features and (features.get("is_hdr") or features.get("is_motion")))


def _option_selection_missing(features: dict, preserve_motion: bool | None, preserve_hdr: bool | None) -> bool:
    return (
        (features.get("is_motion") and preserve_motion is None)
        or (features.get("is_hdr") and preserve_hdr is None)
    )


def _options_payload(task_id: str, features: dict, preserve_motion: bool | None, preserve_hdr: bool | None) -> dict:
    return {
        "needs_options": True,
        "task_id": task_id,
        "features": features,
        "preserve_motion": _preserve_default(preserve_motion),
        "preserve_hdr": _preserve_default(preserve_hdr),
    }


def _preserve_default(value: bool | None) -> bool:
    return True if value is None else bool(value)


def _task_payload_from_waiting_task(
    *,
    task_id: str,
    state,
    task: dict,
    filepath: str,
    style_config,
    logger,
    logo_preference: str | None,
    preliminary_manufacturer: str | None,
    preserve_motion: bool | None,
    preserve_hdr: bool | None,
) -> TaskPayload:
    return TaskPayload(
        task_id=task_id,
        state=state,
        filepath=filepath,
        lang=task.get("lang", "zh"),
        watermark_type=task["watermark_type"],
        image_quality=int(task.get("image_quality") or 85),
        burn_after_read=str(task.get("burn_after_read") or "0"),
        logo_preference=logo_preference,
        style_config=style_config,
        logger=logger,
        preliminary_manufacturer=preliminary_manufacturer,
        preserve_motion=_preserve_default(preserve_motion),
        preserve_hdr=_preserve_default(preserve_hdr),
    )


def _read_image_dimensions(filepath: str) -> tuple[int, int] | None:
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)
            if len(header) < 8:
                return None

            if header[:3] == b"\xff\xd8\xff":
                f.seek(2)
                while True:
                    chunk = f.read(4)
                    if len(chunk) < 4:
                        break
                    ff, marker_lo, seg_len = struct.unpack(">BBH", chunk)
                    if ff != 0xFF:
                        break
                    if marker_lo < 0xC0 or marker_lo > 0xCF or marker_lo in (0xC4, 0xC8, 0xCC):
                        f.seek(seg_len - 2, 1)
                        continue
                    seg_data = f.read(seg_len - 2)
                    if len(seg_data) >= 5:
                        return (struct.unpack(">H", seg_data[3:5])[0], struct.unpack(">H", seg_data[1:3])[0])
                    break

            elif header[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", header[16:24])
    except Exception:
        return None
    return None


def _check_image_pixel_limit(filepath: str) -> None:
    dims = _read_image_dimensions(filepath)
    if dims is None:
        return
    width, height = dims
    if width * height > ImageConstants.MAX_IMAGE_PIXELS:
        raise WatermarkError(WatermarkErrorCode.IMAGE_TOO_LARGE, detail=f"{width}x{height}")


def _save_upload(file, upload_folder: str) -> str:
    timestamp = datetime.fromtimestamp(int(time.time())).strftime("%Y-%m-%d_%H-%M-%S")
    filename = secure_filename(file.filename)
    if not filename or "." not in filename:
        extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
        filename_with_timestamp = f"upload_{timestamp}.{extension}"
    else:
        stem, extension = filename.rsplit(".", 1)
        filename_with_timestamp = f"{stem}_{timestamp}.{extension}"
    filepath = os.path.join(upload_folder, filename_with_timestamp)
    file.save(filepath)
    return filepath


def handle_upload(*, files, form, args, config, state, style_config: dict, logger) -> WorkflowResponse:
    cleanup_old_tasks(state)
    lang = normalize_lang(args.get("lang", "zh"))

    if "file" not in files:
        return WorkflowResponse({"error": get_error_message("no_file_uploaded", lang)}, 400)

    file = files["file"]
    if file.filename == "":
        return WorkflowResponse({"error": get_error_message("no_file_selected", lang)}, 400)

    if not allowed_file(file.filename, config["ALLOWED_EXTENSIONS"]):
        return WorkflowResponse({"error": get_error_message("invalid_file_type", lang)}, 400)

    default_style = str(get_default_style_id(style_config)) if style_config else "1"
    watermark_type = form.get("watermark_type", default_style)
    burn_after_read = form.get("burn_after_read", "0")
    image_quality = form.get("image_quality", "high")
    logo_preference = form.get("logo_preference")
    preserve_motion = _requested_bool(form, "preserve_motion")
    preserve_hdr = _requested_bool(form, "preserve_hdr")

    try:
        watermark_type_int = int(watermark_type)
    except (TypeError, ValueError):
        return WorkflowResponse({"error": get_error_message("unexpected_error", lang)}, 400)
    if not is_style_enabled(style_config, watermark_type_int):
        return WorkflowResponse({"error": get_error_message("unexpected_error", lang)}, 400)

    filepath = _save_upload(file, config["UPLOAD_FOLDER"])
    try:
        _check_image_pixel_limit(filepath)
    except WatermarkError:
        os.remove(filepath)
        error = get_error_message(
            "image_too_large",
            lang,
            limit=format_pixel_limit(ImageConstants.MAX_IMAGE_PIXELS, lang),
        )
        return WorkflowResponse({"error": error}, 400)

    image_quality_int = normalize_image_quality(image_quality)
    manufacturer = detect_manufacturer(filepath, logger)
    features = detect_image_features(filepath)
    pending_task = {
        "progress": 0.0,
        "filepath": filepath,
        "lang": lang,
        "watermark_type": watermark_type_int,
        "image_quality": image_quality_int,
        "burn_after_read": burn_after_read,
        "features": features,
        "preliminary_manufacturer": manufacturer,
        "preserve_motion": preserve_motion,
        "preserve_hdr": preserve_hdr,
    }

    if manufacturer and "xiaomi" in manufacturer.lower():
        normalized_preference = (logo_preference or "").lower()
        if normalized_preference not in {"xiaomi", "leica"}:
            task_id = task_lifecycle.create_waiting_logo_task(state, pending_task)
            return WorkflowResponse({"needs_logo_choice": True, "task_id": task_id}, 200)
        logo_preference = normalized_preference

    if _has_media_options(features) and _option_selection_missing(features, preserve_motion, preserve_hdr):
        task_id = task_lifecycle.create_waiting_options_task(
            state,
            {
                **pending_task,
                "logo_preference": logo_preference,
                "preserve_motion": _preserve_default(preserve_motion),
                "preserve_hdr": _preserve_default(preserve_hdr),
            },
        )
        return WorkflowResponse(_options_payload(task_id, features, preserve_motion, preserve_hdr), 200)

    task_id = submit_task(
        TaskPayload(
            task_id="",
            state=state,
            filepath=filepath,
            lang=lang,
            watermark_type=watermark_type_int,
            image_quality=image_quality_int,
            burn_after_read=burn_after_read,
            logo_preference=logo_preference,
            style_config=style_config,
            logger=logger,
            preliminary_manufacturer=manufacturer,
            preserve_motion=_preserve_default(preserve_motion),
            preserve_hdr=_preserve_default(preserve_hdr),
        )
    )
    return WorkflowResponse({"task_id": task_id}, 202)


def confirm_logo_choice(*, payload: dict, state, style_config: dict, logger) -> WorkflowResponse:
    task_id = str(payload.get("task_id", "")).strip()
    logo_preference = str(payload.get("logo_preference", "")).strip().lower()

    if not task_id:
        return WorkflowResponse({"error": "task_id is required"}, 400)
    if logo_preference not in {"xiaomi", "leica"}:
        return WorkflowResponse({"error": "logo_preference must be xiaomi or leica"}, 400)

    task = state.get_task(task_id)
    if not task:
        return WorkflowResponse({"status": "unknown"}, 404)
    if task.get("status") != "needs_logo":
        return WorkflowResponse({"error": "task is not waiting for logo choice"}, 409)

    filepath = task.get("filepath")
    lang = task.get("lang", "zh")
    if not filepath or not os.path.exists(filepath):
        return WorkflowResponse({"error": get_error_message("file_not_found", lang)}, 404)

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return WorkflowResponse({"error": get_error_message("unexpected_error", lang)}, 400)

    features = task.get("features") or {}
    preserve_motion = task.get("preserve_motion")
    preserve_hdr = task.get("preserve_hdr")
    preliminary_manufacturer = task.get("preliminary_manufacturer")
    if _has_media_options(features) and _option_selection_missing(features, preserve_motion, preserve_hdr):
        task_lifecycle.mark_waiting_options(state, task_id, logo_preference=logo_preference)
        return WorkflowResponse(_options_payload(task_id, features, preserve_motion, preserve_hdr), 200)

    submit_existing_task(
        task_id,
        _task_payload_from_waiting_task(
            task_id=task_id,
            state=state,
            task=task,
            filepath=filepath,
            logo_preference=logo_preference,
            style_config=style_config,
            logger=logger,
            preliminary_manufacturer=preliminary_manufacturer,
            preserve_motion=preserve_motion,
            preserve_hdr=preserve_hdr,
        ),
    )
    return WorkflowResponse({"task_id": task_id}, 202)


def confirm_options(*, payload: dict, state, style_config: dict, logger) -> WorkflowResponse:
    task_id = str(payload.get("task_id", "")).strip()
    if not task_id:
        return WorkflowResponse({"error": "task_id is required"}, 400)

    task = state.get_task(task_id)
    if not task:
        return WorkflowResponse({"status": "unknown"}, 404)
    if task.get("status") != "needs_options":
        return WorkflowResponse({"error": "task is not waiting for options"}, 409)

    preserve_motion = _json_bool(
        payload,
        "preserve_motion",
        _preserve_default(task.get("preserve_motion")),
    )
    preserve_hdr = _json_bool(
        payload,
        "preserve_hdr",
        _preserve_default(task.get("preserve_hdr")),
    )

    filepath = task.get("filepath")
    lang = task.get("lang", "zh")
    if not filepath or not os.path.exists(filepath):
        return WorkflowResponse({"error": get_error_message("file_not_found", lang)}, 404)

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return WorkflowResponse({"error": get_error_message("unexpected_error", lang)}, 400)

    manufacturer = task.get("preliminary_manufacturer") or detect_manufacturer(filepath, logger)
    submit_existing_task(
        task_id,
        _task_payload_from_waiting_task(
            task_id=task_id,
            state=state,
            task=task,
            filepath=filepath,
            logo_preference=task.get("logo_preference"),
            style_config=style_config,
            logger=logger,
            preliminary_manufacturer=manufacturer,
            preserve_motion=preserve_motion,
            preserve_hdr=preserve_hdr,
        ),
    )
    return WorkflowResponse({"task_id": task_id}, 202)


def get_preview_file(*, filename: str, args, upload_folder: str, is_browser: bool) -> PreviewFile:
    lang = normalize_lang(args.get("lang", "zh"))
    safe_filename = secure_filename(filename)
    if not verify_token(
        safe_filename,
        args.get("token", ""),
        args.get("expires", ""),
        action="preview",
    ):
        if is_browser:
            return PreviewFile(status_code=404, render_deleted=True)
        return PreviewFile(status_code=403, error=get_error_message("link_expired", lang))

    file_path = os.path.join(upload_folder, safe_filename)
    if not os.path.exists(file_path):
        if is_browser:
            return PreviewFile(status_code=404, render_deleted=True)
        return PreviewFile(status_code=404, error=get_error_message("file_not_found", lang))

    return PreviewFile(status_code=200, file_path=file_path)


def get_motion_video(*, filename: str, args, upload_folder: str, logger) -> MotionVideo:
    lang = normalize_lang(args.get("lang", "zh"))
    safe_filename = secure_filename(filename)
    if not verify_token(
        safe_filename,
        args.get("token", ""),
        args.get("expires", ""),
        action="motion_video",
    ):
        return MotionVideo(status_code=403, error=get_error_message("link_expired", lang))

    file_path = os.path.join(upload_folder, safe_filename)
    if not os.path.exists(file_path):
        return MotionVideo(status_code=404, error=get_error_message("file_not_found", lang))

    from media.motion_photo import find_motion_video_start

    try:
        video_start = find_motion_video_start(file_path)
        file_size = os.path.getsize(file_path)
    except Exception:
        logger.exception("Failed to extract motion video from %s", safe_filename)
        return MotionVideo(status_code=500, error=get_error_message("unexpected_error", lang))

    if video_start is None or video_start >= file_size:
        return MotionVideo(status_code=404, error="Not a motion photo")

    return MotionVideo(
        status_code=200,
        file_path=file_path,
        filename=safe_filename,
        video_start=video_start,
        file_size=file_size,
    )
