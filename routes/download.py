import os
import tempfile
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from constants import AppConstants
from extensions import limiter
from services.i18n import get_error_message, normalize_lang

bp = Blueprint("download", __name__)


@bp.route("/download_zip", methods=["POST"])
@limiter.limit(AppConstants.ZIP_RATE_LIMIT)
def download_zip():
    lang = normalize_lang(request.args.get("lang", "zh"))
    data = request.json or {}
    filenames = data.get("filenames", [])

    if not filenames:
        return jsonify(error=get_error_message("zip_no_files", lang)), 400

    if len(filenames) > AppConstants.ZIP_MAX_FILES:
        return jsonify(error=get_error_message("zip_too_many_files", lang)), 400

    upload_folder = os.path.realpath(current_app.config["UPLOAD_FOLDER"])

    count = len(filenames)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Packed_Watermark_Images_{count}_{timestamp}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    try:
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for fname in filenames:
                safe_fname = secure_filename(fname)
                if not safe_fname:
                    continue
                full_path = os.path.realpath(os.path.join(upload_folder, safe_fname))
                if not full_path.startswith(upload_folder + os.sep):
                    current_app.logger.warning("Path traversal blocked: %s", fname)
                    continue
                if os.path.isfile(full_path):
                    zipf.write(full_path, arcname=safe_fname)
                else:
                    current_app.logger.warning("Skipping zip for missing file: %s", safe_fname)
    except Exception:
        current_app.logger.exception("Zip creation failed")
        return jsonify(error=get_error_message("zip_create_failed", lang)), 500

    zip_url = f"/download_temp_zip/{zip_filename}"
    return jsonify(zip_url=zip_url)


@bp.route("/download_temp_zip/<filename>")
def download_temp_zip(filename):
    lang = normalize_lang(request.args.get("lang", "zh"))
    safe_filename_str = secure_filename(filename)
    if not safe_filename_str:
        return jsonify(error=get_error_message("file_not_found", lang)), 400
    file_path = os.path.join(tempfile.gettempdir(), safe_filename_str)
    if not os.path.isfile(file_path):
        return jsonify(error=get_error_message("file_not_found", lang)), 404
    return send_file(file_path, as_attachment=True, download_name=safe_filename_str)
