import os
import tempfile
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from constants import AppConstants
from extensions import limiter

bp = Blueprint("download", __name__)


@bp.route("/download_zip", methods=["POST"])
@limiter.limit(AppConstants.ZIP_RATE_LIMIT)
def download_zip():
    data = request.json or {}
    filenames = data.get("filenames", [])

    if not filenames:
        return jsonify(error="No files provided"), 400

    count = len(filenames)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Packed_Watermark_Images_{count}_{timestamp}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    try:
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for fname in filenames:
                safe_fname = secure_filename(fname)
                full_path = os.path.join(current_app.config["UPLOAD_FOLDER"], safe_fname)
                if os.path.exists(full_path) and os.path.isfile(full_path):
                    zipf.write(full_path, arcname=safe_fname)
                else:
                    current_app.logger.warning("Skipping zip for invalid file: %s", fname)
    except Exception as e:
        current_app.logger.error("Zip creation failed: %s", str(e))
        return jsonify(error=str(e)), 500

    zip_url = f"/download_temp_zip/{zip_filename}"
    return jsonify(zip_url=zip_url)


@bp.route("/download_temp_zip/<filename>")
def download_temp_zip(filename):
    safe_filename = secure_filename(filename)
    file_path = os.path.join(tempfile.gettempdir(), safe_filename)
    current_app.logger.info("zip file path: %s", file_path)
    if not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path, as_attachment=True, download_name=safe_filename)

