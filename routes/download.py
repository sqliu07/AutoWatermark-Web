import glob
import os
import threading
import tempfile
import zipfile

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file
from werkzeug.utils import secure_filename

from constants import AppConstants
from extensions import limiter
from routes._utils import is_browser_request
from services.download_token import build_signed_url, verify_token
from services.filenames import unique_archive_name
from services.i18n import get_error_message, normalize_lang

bp = Blueprint("download", __name__)

# A single application process owns the upload directory and ZIP quota.
_zip_creation_lock = threading.Lock()


@bp.route("/download_zip", methods=["GET"])
def download_zip_entry_redirect():
    return redirect("/")


@bp.route("/download_zip", methods=["POST"])
@limiter.limit(AppConstants.ZIP_RATE_LIMIT)
def download_zip():
    lang = normalize_lang(request.args.get("lang", "zh"))
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error=get_error_message("zip_no_files", lang)), 400
    items = data.get("items", [])

    if not isinstance(items, list) or not items:
        return jsonify(error=get_error_message("zip_no_files", lang)), 400

    if len(items) > AppConstants.ZIP_MAX_FILES:
        return jsonify(error=get_error_message("zip_too_many_files", lang)), 400

    filenames = set()
    for item in items:
        if not isinstance(item, dict):
            return jsonify(error=get_error_message("zip_no_files", lang)), 400
        fn = item.get("filename", "")
        if (not isinstance(fn, str) or not fn or secure_filename(fn) != fn
                or fn.rsplit(".", 1)[-1].lower() not in AppConstants.ALLOWED_EXTENSIONS):
            return jsonify(error=get_error_message("zip_no_files", lang)), 400
        burn = str(item.get("burn", "0")).strip()
        token = item.get("token", "")
        if (burn != "0" or not isinstance(token, str) or not token.isascii()
                or not verify_token(fn, token, item.get("expires", ""), action="download", burn=burn)):
            return jsonify(error=get_error_message("link_expired", lang)), 403
        filenames.add(fn)

    upload_folder = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    max_bytes = current_app.config.get("ZIP_MAX_TOTAL_BYTES", 256 * 1024 * 1024)
    quota = current_app.config.get("ZIP_TEMP_QUOTA_BYTES", 1024 * 1024 * 1024)
    if not _zip_creation_lock.acquire(blocking=False):
        return jsonify(error=get_error_message("zip_create_failed", lang)), 503
    zip_path = None
    complete = False
    try:
        sources = []
        archive_names = set()
        total_bytes = 0
        for fname in sorted(filenames):
            full_path = os.path.realpath(os.path.join(upload_folder, fname))
            if not full_path.startswith(upload_folder + os.sep) or not os.path.isfile(full_path):
                return jsonify(error=get_error_message("file_not_found", lang)), 404
            size = os.path.getsize(full_path)
            total_bytes += size
            display_name = unique_archive_name(current_app.extensions["state"].get_download_name(full_path), archive_names)
            sources.append((display_name, full_path, size))
        if total_bytes > max_bytes:
            return jsonify(error=get_error_message("zip_too_many_files", lang)), 413
        # Include central directory, local headers and UTF-8 filenames in quota.
        reserved_bytes = total_bytes + 22 + sum(128 + 2 * len(name.encode("utf-8")) for name, _, _ in sources)
        used_bytes = 0
        for path in glob.glob(os.path.join(tempfile.gettempdir(), "watermark_*.zip")):
            try:
                used_bytes += os.path.getsize(path)
            except FileNotFoundError:
                pass  # The cleaner may remove expired archives.
        if used_bytes + reserved_bytes > quota:
            return jsonify(error=get_error_message("zip_create_failed", lang)), 503
        fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="watermark_")
        os.close(fd)
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for name, path, expected_size in sources:
                # Bound copies even if a source grows after the size check.
                with open(path, "rb") as source, zipf.open(name, "w") as target:
                    remaining = expected_size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise OSError("ZIP source changed during creation")
                        target.write(chunk)
                        remaining -= len(chunk)
                    if source.read(1):
                        raise OSError("ZIP source changed during creation")
        zip_filename = os.path.basename(zip_path)
        complete = True
    except Exception:
        current_app.logger.exception("Zip creation failed")
        return jsonify(error=get_error_message("zip_create_failed", lang)), 500
    finally:
        if zip_path and not complete:
            try:
                os.remove(zip_path)
            except OSError:
                current_app.logger.warning("Unable to remove partial ZIP: %s", zip_path, exc_info=True)
        _zip_creation_lock.release()

    # 生成带签名的 ZIP 下载 URL
    zip_url = build_signed_url(f"/api/download_temp_zip/{zip_filename}", zip_filename, action="zip")
    return jsonify(zip_url=zip_url)


@bp.route("/download_temp_zip/<filename>")
def download_temp_zip(filename):
    lang = normalize_lang(request.args.get("lang", "zh"))
    token = request.args.get("token", "")
    expires = request.args.get("expires", "")
    is_browser = is_browser_request()

    safe_filename_str = secure_filename(filename)
    if not safe_filename_str.startswith("watermark_") or not safe_filename_str.endswith(".zip"):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("file_not_found", lang)), 400

    if not verify_token(safe_filename_str, token, expires, action="zip"):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("link_expired", lang)), 403

    file_path = os.path.join(tempfile.gettempdir(), safe_filename_str)
    if not os.path.isfile(file_path):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("file_not_found", lang)), 404
    return send_file(file_path, as_attachment=True, download_name="AutoWatermark.zip")
