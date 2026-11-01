from __future__ import annotations

import os
import struct
from dataclasses import dataclass
import tempfile
from typing import Any

from PIL import Image
from werkzeug.utils import secure_filename

from constants import AppConstants, ImageConstants, format_pixel_limit
from imaging.safety import validate_input_size
from werkzeug.exceptions import ServiceUnavailable, RequestEntityTooLarge
from errors import WatermarkError
from process import detect_image_features
from services import task_lifecycle
from services.download_token import verify_token
from services.i18n import get_error_message, normalize_lang
from services.path_safety import resolve_under_root
from services.previews import preview_source
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
        original_name=task.get("original_name"),
    )


def _read_image_dimensions(filepath: str, upload_folder: str) -> tuple[int, int] | None:
    safe_path = resolve_under_root(upload_folder, filepath)
    if safe_path is None:
        return None
    try:
        with open(safe_path, "rb") as f:
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


def _check_image_pixel_limit(filepath: str, upload_folder: str) -> None:
    dims = _read_image_dimensions(filepath, upload_folder)
    if dims is None:
        raise ValueError("Only JPEG and PNG uploads are accepted")
    width, height = dims
    validate_input_size((width, height))
    # Restrict decoder selection before any EXIF tool or background processing.
    with Image.open(filepath, formats=("JPEG", "PNG")) as image:
        validate_input_size(image.size)
        image.verify()


def _save_upload(file, upload_folder: str) -> str:
    # The storage basename is random; preserve the validated source extension
    # even when secure_filename would strip a non-ASCII basename entirely.
    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if extension not in AppConstants.ALLOWED_EXTENSIONS:
        extension = "jpg"
    fd, filepath = tempfile.mkstemp(prefix="photo_", suffix="." + extension, dir=upload_folder)
    try:
        with os.fdopen(fd, "wb") as target:
            size = 0
            while chunk := file.stream.read(1024 * 1024):
                size += len(chunk)
                if size > AppConstants.MAX_CONTENT_LENGTH:
                    raise RequestEntityTooLarge()
                target.write(chunk)
    except BaseException:
        os.unlink(filepath)
        raise
    return os.path.abspath(filepath)


def handle_upload(*, files, form, args, config, state, style_config: dict, logger) -> WorkflowResponse:
    # Include metadata parsing and waiting prompts in admission, rather than
    # admitting unlimited work before it reaches the bounded executor.
    if not state.upload_lock.acquire(blocking=False):
        raise ServiceUnavailable("Upload processing is busy; try again later")
    try:
        cleanup_old_tasks(state)
        if state.count_tasks_by_status("queued", "processing", "needs_logo", "needs_options") >= AppConstants.MAX_PENDING_TASKS:
            raise ServiceUnavailable("Task capacity reached; try again later")
        return _handle_upload(
            files=files, form=form, args=args, config=config, state=state,
            style_config=style_config, logger=logger,
        )
    finally:
        state.upload_lock.release()


def _handle_upload(*, files, form, args, config, state, style_config: dict, logger) -> WorkflowResponse:
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

    with os.scandir(config["UPLOAD_FOLDER"]) as entries:
        used = 0
        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False):
                    used += entry.stat(follow_symlinks=False).st_size
            except FileNotFoundError:
                pass  # The cleaner can remove expired files concurrently.
    # Reserve enough space for the largest accepted request before writing.
    if used + AppConstants.MAX_CONTENT_LENGTH > AppConstants.MAX_UPLOAD_STORAGE_BYTES:
        raise ServiceUnavailable("Upload storage is full; try again later")
    filepath = _save_upload(file, config["UPLOAD_FOLDER"])
    try:
        _check_image_pixel_limit(filepath, config["UPLOAD_FOLDER"])
    except WatermarkError:
        safe_path = resolve_under_root(config["UPLOAD_FOLDER"], filepath)
        if safe_path is not None:
            os.remove(safe_path)
        error = get_error_message(
            "image_too_large",
            lang,
            limit=format_pixel_limit(ImageConstants.MAX_IMAGE_PIXELS, lang),
        )
        return WorkflowResponse({"error": error}, 400)
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError):
        os.remove(filepath)
        return WorkflowResponse({"error": get_error_message("invalid_file_type", lang)}, 400)

    image_quality_int = normalize_image_quality(image_quality)
    manufacturer = detect_manufacturer(filepath, logger)
    features = detect_image_features(filepath)
    pending_task = {
        "original_name": file.filename,
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
            original_name=file.filename,
        )
    )
    return WorkflowResponse({"task_id": task_id}, 202)


def confirm_logo_choice(*, payload: dict, state, upload_folder: str, style_config: dict, logger) -> WorkflowResponse:
    task_id = payload.get("task_id", "")
    if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 128:
        return WorkflowResponse({"error": "task_id must be a non-empty string"}, 400)
    task_id = task_id.strip()
    logo_preference = str(payload.get("logo_preference", "")).strip().lower()

    if not task_id:
        return WorkflowResponse({"error": "task_id is required"}, 400)
    if logo_preference not in {"xiaomi", "leica"}:
        return WorkflowResponse({"error": "logo_preference must be xiaomi or leica"}, 400)

    task = state.get_task(task_id)
    if not task:
        return WorkflowResponse({"status": "unknown"}, 404)
    if task.get("status") != task_lifecycle.TaskStatus.NEEDS_LOGO:
        return WorkflowResponse({"error": "task is not waiting for logo choice"}, 409)

    filepath = task.get("filepath")
    lang = task.get("lang", "zh")
    safe_filepath = resolve_under_root(upload_folder, filepath or "")
    if safe_filepath is None or not os.path.exists(safe_filepath):
        return WorkflowResponse({"error": get_error_message("file_not_found", lang)}, 404)

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return WorkflowResponse({"error": get_error_message("unexpected_error", lang)}, 400)

    features = task.get("features") or {}
    preserve_motion = task.get("preserve_motion")
    preserve_hdr = task.get("preserve_hdr")
    preliminary_manufacturer = task.get("preliminary_manufacturer")
    if _has_media_options(features) and _option_selection_missing(features, preserve_motion, preserve_hdr):
        if not state.update_task(
            task_id, expected_status=task_lifecycle.TaskStatus.NEEDS_LOGO,
            status=task_lifecycle.TaskStatus.NEEDS_OPTIONS,
            stage=task_lifecycle.TaskStage.AWAITING_OPTIONS, progress=0.0,
            logo_preference=logo_preference,
        ):
            return WorkflowResponse({"error": "task is not waiting for logo choice"}, 409)
        return WorkflowResponse(_options_payload(task_id, features, preserve_motion, preserve_hdr), 200)

    if not state.update_task(
        task_id, expected_status=task_lifecycle.TaskStatus.NEEDS_LOGO,
        status=task_lifecycle.TaskStatus.QUEUED, stage=task_lifecycle.TaskStage.QUEUED,
    ):
        return WorkflowResponse({"error": "task is not waiting for logo choice"}, 409)
    submit_existing_task(
        task_id,
        _task_payload_from_waiting_task(
            task_id=task_id,
            state=state,
            task=task,
            filepath=safe_filepath,
            logo_preference=logo_preference,
            style_config=style_config,
            logger=logger,
            preliminary_manufacturer=preliminary_manufacturer,
            preserve_motion=preserve_motion,
            preserve_hdr=preserve_hdr,
        ),
    )
    return WorkflowResponse({"task_id": task_id}, 202)


def confirm_options(*, payload: dict, state, upload_folder: str, style_config: dict, logger) -> WorkflowResponse:
    task_id = payload.get("task_id", "")
    if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 128:
        return WorkflowResponse({"error": "task_id must be a non-empty string"}, 400)
    task_id = task_id.strip()
    if not task_id:
        return WorkflowResponse({"error": "task_id is required"}, 400)

    task = state.get_task(task_id)
    if not task:
        return WorkflowResponse({"status": "unknown"}, 404)
    if task.get("status") != task_lifecycle.TaskStatus.NEEDS_OPTIONS:
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
    safe_filepath = resolve_under_root(upload_folder, filepath or "")
    if safe_filepath is None or not os.path.exists(safe_filepath):
        return WorkflowResponse({"error": get_error_message("file_not_found", lang)}, 404)

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return WorkflowResponse({"error": get_error_message("unexpected_error", lang)}, 400)

    manufacturer = task.get("preliminary_manufacturer") or detect_manufacturer(safe_filepath, logger)
    if not state.update_task(
        task_id, expected_status=task_lifecycle.TaskStatus.NEEDS_OPTIONS,
        status=task_lifecycle.TaskStatus.QUEUED, stage=task_lifecycle.TaskStage.QUEUED,
    ):
        return WorkflowResponse({"error": "task is not waiting for options"}, 409)
    submit_existing_task(
        task_id,
        _task_payload_from_waiting_task(
            task_id=task_id,
            state=state,
            task=task,
            filepath=safe_filepath,
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
    if not safe_filename or not allowed_file(safe_filename, AppConstants.ALLOWED_EXTENSIONS):
        if is_browser:
            return PreviewFile(status_code=404, render_deleted=True)
        return PreviewFile(status_code=404, error=get_error_message("file_not_found", lang))
    if not verify_token(
        safe_filename,
        args.get("token", ""),
        args.get("expires", ""),
        action="preview",
    ):
        if is_browser:
            return PreviewFile(status_code=404, render_deleted=True)
        return PreviewFile(status_code=403, error=get_error_message("link_expired", lang))

    file_path = resolve_under_root(upload_folder, safe_filename)
    source_path = preview_source(file_path) if file_path is not None else None
    if (os.path.islink(os.path.join(upload_folder, safe_filename))
            or file_path is None or not os.path.isfile(file_path)
            or (source_path is not None and not os.path.isfile(source_path))):
        if is_browser:
            return PreviewFile(status_code=404, render_deleted=True)
        return PreviewFile(status_code=404, error=get_error_message("file_not_found", lang))

    return PreviewFile(status_code=200, file_path=file_path)


def get_motion_video(*, filename: str, args, upload_folder: str, logger) -> MotionVideo:
    lang = normalize_lang(args.get("lang", "zh"))
    safe_filename = secure_filename(filename)
    if not safe_filename or not allowed_file(safe_filename, AppConstants.ALLOWED_EXTENSIONS):
        return MotionVideo(status_code=404, error=get_error_message("file_not_found", lang))
    if not verify_token(
        safe_filename,
        args.get("token", ""),
        args.get("expires", ""),
        action="motion_video",
    ):
        return MotionVideo(status_code=403, error=get_error_message("link_expired", lang))

    file_path = resolve_under_root(upload_folder, safe_filename)
    if file_path is None or not os.path.exists(file_path):
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
