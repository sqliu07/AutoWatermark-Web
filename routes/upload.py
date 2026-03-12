import os
import time
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, render_template, send_file
from werkzeug.utils import secure_filename

from config.constants import AppConstants
from services.i18n import get_message, get_common_message, normalize_lang
from infra.sqlite_task_store import get_task, schedule_burn_file
from infra.extensions import limiter
from services.tasks import (
    allowed_file,
    detect_manufacturer,
    normalize_image_quality,
    submit_task,
)
from services.watermark_styles import get_default_style_id, is_style_enabled

bp = Blueprint("upload", __name__)


@bp.route("/upload", methods=["POST"])
@limiter.limit(AppConstants.UPLOAD_RATE_LIMIT)
def upload_file():
    state = current_app.extensions["state"]
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    db_path = current_app.config["DATABASE_PATH"]
    lang = normalize_lang(request.args.get("lang", "zh"))

    if "file" not in request.files:
        return jsonify(error=get_message("no_file_uploaded", lang)), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify(error=get_message("no_file_selected", lang)), 400

    if not allowed_file(file.filename, current_app.config["ALLOWED_EXTENSIONS"]):
        return jsonify(error=get_message("invalid_file_type", lang)), 400

    style_config = current_app.extensions.get("watermark_styles", {})
    default_style = str(get_default_style_id(style_config)) if style_config else "1"
    watermark_type = request.form.get("watermark_type", default_style)
    burn_after_read = request.form.get("burn_after_read", "0")
    image_quality = request.form.get("image_quality", "high")
    logo_preference = request.form.get("logo_preference")

    image_quality_int = normalize_image_quality(image_quality)

    try:
        watermark_type_int = int(watermark_type)
    except (TypeError, ValueError):
        return jsonify(error=get_common_message("unexpected_error", lang)), 400

    if not is_style_enabled(style_config, watermark_type_int):
        return jsonify(error=get_common_message("unexpected_error", lang)), 400

    filename = secure_filename(file.filename)
    stem = Path(filename).stem or "image"
    extension = Path(filename).suffix.lower()
    temp_filepath = os.path.join(upload_dir, f"upload_{uuid.uuid4().hex}{extension}")
    filepath = None

    file.save(temp_filepath)
    try:
        manufacturer = detect_manufacturer(temp_filepath)
        if manufacturer and "xiaomi" in manufacturer.lower():
            normalized_preference = (logo_preference or "").lower()
            if normalized_preference not in {"xiaomi", "leica"}:
                if os.path.exists(temp_filepath):
                    os.remove(temp_filepath)
                return jsonify({"needs_logo_choice": True}), 200
            logo_preference = normalized_preference

        final_filename = f"{stem}_{uuid.uuid4().hex}{extension}"
        filepath = os.path.join(upload_dir, final_filename)
        os.replace(temp_filepath, filepath)

        task_id = submit_task(
            state,
            db_path,
            filepath,
            lang,
            watermark_type_int,
            image_quality_int,
            burn_after_read,
            logo_preference,
            style_config,
            current_app.logger,
        )
    except Exception:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        raise

    return jsonify({"task_id": task_id}), 202


@bp.route("/status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    task = get_task(current_app.config["DATABASE_PATH"], task_id)
    if not task:
        return jsonify({"status": "unknown"}), 404
    return jsonify(task)


@bp.route("/upload/<filename>")
def upload_file_served(filename):
    lang = normalize_lang(request.args.get("lang", "zh"))
    burn_after_read = request.args.get("burn", "0")

    filename = secure_filename(filename)
    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

    if not os.path.exists(file_path):
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            translations = current_app.extensions.get("translations", {})
            return render_template("image_deleted.html", lang=lang, translations=translations), 404
        return jsonify(error="File not found"), 404

    if str(burn_after_read).strip() == "1":
        schedule_burn_file(
            current_app.config["DATABASE_PATH"],
            file_path,
            time.time() + AppConstants.BURN_TTL_SECONDS,
            time.time(),
        )

    return send_file(file_path)
