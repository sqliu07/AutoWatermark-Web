import os
import time
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, render_template, send_file
from werkzeug.utils import secure_filename

from extensions import limiter
from services.i18n import get_message, get_common_message, normalize_lang
from services.tasks import (
    allowed_file,
    cleanup_old_tasks,
    detect_manufacturer,
    normalize_image_quality,
    submit_task,
)
from services.watermark_styles import get_default_style_id, is_style_enabled

bp = Blueprint("upload", __name__)


@bp.route("/upload", methods=["POST"])
@limiter.limit(lambda: current_app.config["app_config"].upload_rate_limit)
def upload_file():
    config = current_app.config["app_config"]
    state = current_app.extensions["state"]
    cleanup_old_tasks(state, config)

    lang = normalize_lang(request.args.get("lang", "zh"))

    if "file" not in request.files:
        return jsonify(error=get_message("no_file_uploaded", lang)), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify(error=get_message("no_file_selected", lang)), 400

    if not allowed_file(file.filename, config.allowed_extensions):
        return jsonify(error=get_message("invalid_file_type", lang)), 400

    style_config = current_app.extensions.get("watermark_styles", {})
    default_style = str(get_default_style_id(style_config)) if style_config else "1"
    watermark_type = request.form.get("watermark_type", default_style)
    burn_after_read = request.form.get("burn_after_read", "0")
    image_quality = request.form.get("image_quality", "high")
    logo_preference = request.form.get("logo_preference")

    image_quality_int = normalize_image_quality(image_quality, config)

    if watermark_type is None:
        return jsonify(error="Watermark style not selected!"), 400

    if file and allowed_file(file.filename, config.allowed_extensions):
        timestamp = datetime.fromtimestamp(int(time.time())).strftime("%Y-%m-%d_%H-%M-%S")

        filename = secure_filename(file.filename)
        extension = filename.rsplit(".", 1)[1]
        filename_with_timestamp = f"{filename.rsplit('.', 1)[0]}_{timestamp}.{extension}"
        filepath = config.upload_folder / filename_with_timestamp

        file.save(filepath)

        manufacturer = detect_manufacturer(filepath)
        if manufacturer and "xiaomi" in manufacturer.lower():
            normalized_preference = (logo_preference or "").lower()
            if normalized_preference not in {"xiaomi", "leica"}:
                return jsonify({"needs_logo_choice": True}), 200
            logo_preference = normalized_preference

        try:
            watermark_type_int = int(watermark_type)
        except ValueError:
            return jsonify(error=get_common_message("unexpected_error", lang)), 400
        if not is_style_enabled(style_config, watermark_type_int):
            return jsonify(error=get_common_message("unexpected_error", lang)), 400

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
            config,
        )

        return jsonify({"task_id": task_id}), 202

    return jsonify(error="Invalid file type"), 400


@bp.route("/status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    state = current_app.extensions["state"]
    with state.tasks_lock:
        task = state.tasks.get(task_id)
        if task is not None:
            task = dict(task)
    if not task:
        return jsonify({"status": "unknown"}), 404
    return jsonify(task)


@bp.route("/upload/<filename>")
def upload_file_served(filename):
    config = current_app.config["app_config"]
    lang = normalize_lang(request.args.get("lang", "zh"))
    burn_after_read = request.args.get("burn", "0")

    filename = secure_filename(filename)
    file_path = config.upload_folder / filename

    if not os.path.exists(file_path):
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            translations = current_app.extensions.get("translations", {})
            return render_template("image_deleted.html", lang=lang, translations=translations), 404
        return jsonify(error="File not found"), 404

    if str(burn_after_read).strip() == "1":
        state = current_app.extensions["state"]
        with state.burn_queue_lock:
            state.burn_queue[file_path] = time.time() + config.burn_ttl_seconds

    return send_file(file_path)
