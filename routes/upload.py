import os
import time
from datetime import datetime

import struct

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, send_file, stream_with_context
from werkzeug.utils import secure_filename

from constants import AppConstants, ImageConstants, format_pixel_limit
from errors import WatermarkError, WatermarkErrorCode
from extensions import limiter
from routes._utils import is_browser_request
from services.download_token import verify_token
from services.i18n import get_error_message, normalize_lang
from services.tasks import (
    TaskPayload,
    allowed_file,
    cleanup_old_tasks,
    create_task,
    detect_manufacturer,
    normalize_image_quality,
    submit_existing_task,
    submit_task,
)
from services.watermark_styles import get_default_style_id, is_style_enabled
from process import detect_image_features


def _requested_bool(name: str) -> bool | None:
    value = request.form.get(name)
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
        "preserve_motion": True if preserve_motion is None else bool(preserve_motion),
        "preserve_hdr": True if preserve_hdr is None else bool(preserve_hdr),
    }


def _read_image_dimensions(filepath: str) -> tuple[int, int] | None:
    """从 JPEG / PNG 文件头解析像素尺寸，不依赖 PIL 全局状态。"""
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)
            if len(header) < 8:
                return None

            if header[:3] == b"\xff\xd8\xff":
                # JPEG: 扫描 SOF0 / SOF1 / SOF2 标记段获取尺寸
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
                # PNG: IHDR 块在偏移 16 bytes，宽高各 4 字节
                width, height = struct.unpack(">II", header[16:24])
                return width, height

    except Exception:
        pass
    return None


def _check_image_pixel_limit(filepath: str) -> None:
    """在上传阶段检查图像像素是否超出限制。"""
    dims = _read_image_dimensions(filepath)
    if dims is None:
        return  # 无法解析的文件不拦截，留给处理阶段报错
    width, height = dims
    if width * height > ImageConstants.MAX_IMAGE_PIXELS:
        raise WatermarkError(WatermarkErrorCode.IMAGE_TOO_LARGE, detail=f"{width}x{height}")


bp = Blueprint("upload", __name__)


@bp.route("/upload", methods=["GET"])
def upload_entry_redirect():
    return redirect("/")


@bp.route("/upload", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_file():
    state = current_app.extensions["state"]
    cleanup_old_tasks(state)

    lang = normalize_lang(request.args.get("lang", "zh"))

    if "file" not in request.files:
        return jsonify(error=get_error_message("no_file_uploaded", lang)), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify(error=get_error_message("no_file_selected", lang)), 400

    if not allowed_file(file.filename, current_app.config["ALLOWED_EXTENSIONS"]):
        return jsonify(error=get_error_message("invalid_file_type", lang)), 400

    style_config = current_app.extensions.get("watermark_styles", {})
    default_style = str(get_default_style_id(style_config)) if style_config else "1"
    watermark_type = request.form.get("watermark_type", default_style)
    burn_after_read = request.form.get("burn_after_read", "0")
    image_quality = request.form.get("image_quality", "high")
    logo_preference = request.form.get("logo_preference")
    preserve_motion = _requested_bool("preserve_motion")
    preserve_hdr = _requested_bool("preserve_hdr")

    image_quality_int = normalize_image_quality(image_quality)

    if watermark_type is None:
        return jsonify(error=get_error_message("unexpected_error", lang)), 400

    try:
        watermark_type_int = int(watermark_type)
    except ValueError:
        return jsonify(error=get_error_message("unexpected_error", lang)), 400
    if not is_style_enabled(style_config, watermark_type_int):
        return jsonify(error=get_error_message("unexpected_error", lang)), 400

    if file and allowed_file(file.filename, current_app.config["ALLOWED_EXTENSIONS"]):
        timestamp = datetime.fromtimestamp(int(time.time())).strftime("%Y-%m-%d_%H-%M-%S")

        filename = secure_filename(file.filename)
        if not filename or "." not in filename:
            extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
            filename_with_timestamp = f"upload_{timestamp}.{extension}"
        else:
            extension = filename.rsplit(".", 1)[1]
            filename_with_timestamp = f"{filename.rsplit('.', 1)[0]}_{timestamp}.{extension}"
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename_with_timestamp)

        file.save(filepath)

        try:
            _check_image_pixel_limit(filepath)
        except WatermarkError:
            os.remove(filepath)
            return jsonify(error=get_error_message("image_too_large", lang, limit=format_pixel_limit(ImageConstants.MAX_IMAGE_PIXELS, lang))), 400

        manufacturer = detect_manufacturer(filepath)
        features = detect_image_features(filepath)
        if manufacturer and "xiaomi" in manufacturer.lower():
            normalized_preference = (logo_preference or "").lower()
            if normalized_preference not in {"xiaomi", "leica"}:
                task_id = create_task(
                    state,
                    {
                        "status": "needs_logo",
                        "stage": "awaiting_logo",
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
                    },
                )
                return jsonify({"needs_logo_choice": True, "task_id": task_id}), 200
            logo_preference = normalized_preference

        if _has_media_options(features) and _option_selection_missing(features, preserve_motion, preserve_hdr):
            task_id = create_task(
                state,
                {
                    "status": "needs_options",
                    "stage": "awaiting_options",
                    "progress": 0.0,
                    "filepath": filepath,
                    "lang": lang,
                    "watermark_type": watermark_type_int,
                    "image_quality": image_quality_int,
                    "burn_after_read": burn_after_read,
                    "logo_preference": logo_preference,
                    "features": features,
                    "preliminary_manufacturer": manufacturer,
                    "preserve_motion": True if preserve_motion is None else preserve_motion,
                    "preserve_hdr": True if preserve_hdr is None else preserve_hdr,
                },
            )
            return jsonify(_options_payload(task_id, features, preserve_motion, preserve_hdr)), 200

        task_id = submit_task(TaskPayload(
            task_id="",
            state=state,
            filepath=filepath,
            lang=lang,
            watermark_type=watermark_type_int,
            image_quality=image_quality_int,
            burn_after_read=burn_after_read,
            logo_preference=logo_preference,
            style_config=style_config,
            logger=current_app.logger,
            preliminary_manufacturer=manufacturer,
            preserve_motion=True if preserve_motion is None else preserve_motion,
            preserve_hdr=True if preserve_hdr is None else preserve_hdr,
        ))

        return jsonify({"task_id": task_id}), 202

    return jsonify(error=get_error_message("invalid_file_type", lang)), 400


@bp.route("/upload/confirm_logo", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def confirm_logo_choice():
    state = current_app.extensions["state"]
    style_config = current_app.extensions.get("watermark_styles", {})
    payload = request.get_json(silent=True) or {}
    task_id = str(payload.get("task_id", "")).strip()
    logo_preference = str(payload.get("logo_preference", "")).strip().lower()

    if not task_id:
        return jsonify(error="task_id is required"), 400
    if logo_preference not in {"xiaomi", "leica"}:
        return jsonify(error="logo_preference must be xiaomi or leica"), 400

    task = state.get_task(task_id)
    if not task:
        return jsonify({"status": "unknown"}), 404
    if task.get("status") != "needs_logo":
        return jsonify(error="task is not waiting for logo choice"), 409

    filepath = task.get("filepath")
    if not filepath or not os.path.exists(filepath):
        return jsonify(error=get_error_message("file_not_found", task.get("lang", "zh"))), 404

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return jsonify(error=get_error_message("unexpected_error", task.get("lang", "zh"))), 400

    features = task.get("features") or {}
    preserve_motion = task.get("preserve_motion")
    preserve_hdr = task.get("preserve_hdr")
    preliminary_manufacturer = task.get("preliminary_manufacturer")
    if _has_media_options(features) and _option_selection_missing(features, preserve_motion, preserve_hdr):
        state.update_task(
            task_id,
            status="needs_options",
            stage="awaiting_options",
            progress=0.0,
            logo_preference=logo_preference,
        )
        return jsonify(_options_payload(task_id, features, preserve_motion, preserve_hdr)), 200

    submit_existing_task(task_id, TaskPayload(
        task_id=task_id,
        state=state,
        filepath=filepath,
        lang=task.get("lang", "zh"),
        watermark_type=watermark_type,
        image_quality=int(task.get("image_quality") or 85),
        burn_after_read=str(task.get("burn_after_read") or "0"),
        logo_preference=logo_preference,
        style_config=style_config,
        logger=current_app.logger,
        preliminary_manufacturer=preliminary_manufacturer,
        preserve_motion=True if preserve_motion is None else bool(preserve_motion),
        preserve_hdr=True if preserve_hdr is None else bool(preserve_hdr),
    ))

    return jsonify({"task_id": task_id}), 202


@bp.route("/upload/confirm_logo", methods=["GET"])
def confirm_logo_entry_redirect():
    return redirect("/")


@bp.route("/upload/confirm_options", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def confirm_options():
    """确认 HDR/Motion Photo 选项后继续处理。"""
    state = current_app.extensions["state"]
    style_config = current_app.extensions.get("watermark_styles", {})
    payload = request.get_json(silent=True) or {}
    task_id = str(payload.get("task_id", "")).strip()
    preserve_motion = payload.get("preserve_motion")
    preserve_hdr = payload.get("preserve_hdr")

    if not task_id:
        return jsonify(error="task_id is required"), 400

    task = state.get_task(task_id)
    if not task:
        return jsonify({"status": "unknown"}), 404
    if task.get("status") != "needs_options":
        return jsonify(error="task is not waiting for options"), 409

    preserve_motion = _json_bool(
        payload,
        "preserve_motion",
        True if task.get("preserve_motion") is None else bool(task.get("preserve_motion")),
    )
    preserve_hdr = _json_bool(
        payload,
        "preserve_hdr",
        True if task.get("preserve_hdr") is None else bool(task.get("preserve_hdr")),
    )

    filepath = task.get("filepath")
    if not filepath or not os.path.exists(filepath):
        return jsonify(error=get_error_message("file_not_found", task.get("lang", "zh"))), 404

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return jsonify(error=get_error_message("unexpected_error", task.get("lang", "zh"))), 400

    manufacturer = task.get("preliminary_manufacturer") or detect_manufacturer(filepath)
    logo_preference = task.get("logo_preference")

    submit_existing_task(task_id, TaskPayload(
        task_id=task_id,
        state=state,
        filepath=filepath,
        lang=task.get("lang", "zh"),
        watermark_type=watermark_type,
        image_quality=int(task.get("image_quality") or 85),
        burn_after_read=str(task.get("burn_after_read") or "0"),
        logo_preference=logo_preference,
        style_config=style_config,
        logger=current_app.logger,
        preliminary_manufacturer=manufacturer,
        preserve_motion=preserve_motion,
        preserve_hdr=preserve_hdr,
    ))

    return jsonify({"task_id": task_id}), 202


@bp.route("/status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    if is_browser_request():
        return redirect("/")

    state = current_app.extensions["state"]
    task = state.get_task(task_id)
    if not task:
        return jsonify({"status": "unknown"}), 404
    return jsonify(
        {
            "status": task.get("status"),
            "progress": task.get("progress", 0.0),
            "stage": task.get("stage"),
            "result": task.get("result"),
            "error": task.get("error"),
        }
    )


@bp.route("/upload/<filename>")
def upload_file_served(filename):
    """预览端点：inline 展示，不触发焚烧。"""
    lang = normalize_lang(request.args.get("lang", "zh"))
    token = request.args.get("token", "")
    expires = request.args.get("expires", "")

    filename = secure_filename(filename)
    is_browser = is_browser_request()

    if not verify_token(filename, token, expires, action="preview"):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("link_expired", lang)), 403

    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(file_path):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("file_not_found", lang)), 404

    return send_file(file_path)


@bp.route("/upload/<filename>/video")
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_motion_video(filename):
    """从 Motion Photo 文件中提取视频部分，返回 video/mp4。"""
    lang = normalize_lang(request.args.get("lang", "zh"))
    token = request.args.get("token", "")
    expires = request.args.get("expires", "")

    filename = secure_filename(filename)
    if not verify_token(filename, token, expires, action="motion_video"):
        return jsonify(error=get_error_message("link_expired", lang)), 403

    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(file_path):
        return jsonify(error=get_error_message("file_not_found", lang)), 404

    from media.motion_photo import find_motion_video_start
    try:
        video_start = find_motion_video_start(file_path)
        if video_start is None:
            return jsonify(error="Not a motion photo"), 404

        file_size = os.path.getsize(file_path)
        if video_start >= file_size:
            return jsonify(error="Not a motion photo"), 404

        def generate_video_stream():
            with open(file_path, "rb") as fp:
                fp.seek(video_start)
                while True:
                    chunk = fp.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk

        response = Response(stream_with_context(generate_video_stream()), mimetype="video/mp4")
        response.headers["Content-Length"] = str(file_size - video_start)
        response.headers["Content-Disposition"] = f'inline; filename="{filename}.mp4"'
        return response
    except Exception:
        current_app.logger.exception("Failed to extract motion video from %s", filename)
        return jsonify(error=get_error_message("unexpected_error", lang)), 500
