import os
import time
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, send_file, stream_with_context
from werkzeug.utils import secure_filename

from constants import AppConstants
from extensions import limiter
from routes._utils import is_browser_request
from services.download_token import verify_token
from services.i18n import get_error_message, normalize_lang
from services.tasks import (
    allowed_file,
    cleanup_old_tasks,
    create_task,
    detect_manufacturer,
    normalize_image_quality,
    submit_existing_task,
    submit_task,
)
from services.watermark_styles import get_default_style_id, is_style_enabled

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
        extension = filename.rsplit(".", 1)[1]
        filename_with_timestamp = f"{filename.rsplit('.', 1)[0]}_{timestamp}.{extension}"
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename_with_timestamp)

        file.save(filepath)

        manufacturer = detect_manufacturer(filepath)
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
                    },
                )
                return jsonify({"needs_logo_choice": True, "task_id": task_id}), 200
            logo_preference = normalized_preference

        task_id = submit_task(
            state,
            filepath,
            lang,
            watermark_type_int,
            image_quality_int,
            burn_after_read,
            logo_preference,
            style_config,
            current_app.logger,
        )

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

    submit_existing_task(
        task_id,
        state,
        filepath,
        task.get("lang", "zh"),
        watermark_type,
        int(task.get("image_quality") or 85),
        str(task.get("burn_after_read") or "0"),
        logo_preference,
        style_config,
        current_app.logger,
    )

    return jsonify({"task_id": task_id}), 202


@bp.route("/upload/confirm_logo", methods=["GET"])
def confirm_logo_entry_redirect():
    return redirect("/")


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
    lang = normalize_lang(request.args.get("lang", "zh"))
    burn_after_read = request.args.get("burn", "0")
    token = request.args.get("token", "")
    expires = request.args.get("expires", "")

    filename = secure_filename(filename)

    is_browser = is_browser_request()

    # 签名校验：无 token 或校验失败则拒绝
    if not verify_token(filename, token, expires):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("link_expired", lang)), 403

    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

    if not os.path.exists(file_path):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("file_not_found", lang)), 404

    if str(burn_after_read).strip() == "1":
        state = current_app.extensions["state"]
        state.schedule_burn(file_path, time.time() + AppConstants.BURN_TTL_SECONDS)

    return send_file(file_path)


@bp.route("/upload/<filename>/video")
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_motion_video(filename):
    """从 Motion Photo 文件中提取视频部分，返回 video/mp4。"""
    lang = normalize_lang(request.args.get("lang", "zh"))
    token = request.args.get("token", "")
    expires = request.args.get("expires", "")

    filename = secure_filename(filename)
    if not verify_token(filename, token, expires):
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
