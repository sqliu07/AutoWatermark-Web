import os
import tempfile
import time

from flask import Blueprint, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from constants import AppConstants
from routes._utils import is_browser_request
from services.download_token import verify_token
from services.i18n import get_error_message, normalize_lang
from services.path_safety import protected_state_paths, resolve_under_root
from services.previews import preview_paths

bp = Blueprint("download_file", __name__)


@bp.route("/download/<filename>")
def download_file(filename):
    """下载端点：强制 attachment，支持 burn-after-read（立即删除）。"""
    lang = normalize_lang(request.args.get("lang", "zh"))
    burn_after_read = request.args.get("burn", "0")
    token = request.args.get("token", "")
    expires = request.args.get("expires", "")

    filename = secure_filename(filename)
    is_browser = is_browser_request()

    if (filename.rsplit(".", 1)[-1].lower() not in AppConstants.ALLOWED_EXTENSIONS
            or not verify_token(filename, token, expires, action="download", burn=str(burn_after_read).strip())):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("link_expired", lang)), 403

    upload_folder = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    file_path = os.path.realpath(os.path.join(upload_folder, filename))
    if not file_path.startswith(upload_folder + os.sep) or not os.path.isfile(file_path):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("file_not_found", lang)), 404

    serve_path = file_path
    cleanup_paths = []
    state = current_app.extensions["state"]
    logger = current_app.logger
    display_name = state.get_download_name(file_path)
    if str(burn_after_read).strip() == "1":
        suffix = os.path.splitext(filename)[1]
        fd, burn_path = tempfile.mkstemp(prefix=".burn_", suffix=suffix, dir=current_app.config["UPLOAD_FOLDER"])
        os.close(fd)
        try:
            # Persist before renaming so crashes cannot strand the hidden file.
            expire_at = time.time() + 3600
            state.schedule_burn(burn_path, expire_at)
            protected = protected_state_paths(current_app.config.get("STATE_DB_PATH"))
            for path in preview_paths(file_path).values():
                if os.path.islink(path):
                    continue
                safe_path = resolve_under_root(upload_folder, path)
                if safe_path is not None and safe_path not in protected and os.path.isfile(safe_path):
                    state.schedule_burn(path, expire_at)
                    cleanup_paths.append(path)
            original = state.get_burn_original(file_path)
            if original:
                original = os.path.realpath(original)
                if original.startswith(upload_folder + os.sep) and original != file_path:
                    state.schedule_burn(original, expire_at)
                    cleanup_paths.append(original)
            os.replace(file_path, burn_path)
        except Exception as exc:
            try:
                os.remove(burn_path)
            except OSError:
                pass
            if not isinstance(exc, FileNotFoundError):
                raise
            if is_browser:
                return render_template("image_deleted.html"), 404
            return jsonify(error=get_error_message("file_not_found", lang)), 404
        serve_path = burn_path
        cleanup_paths.append(burn_path)

    def cleanup_burn_files():
        for path in cleanup_paths:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Burn cleanup deferred: %s", os.path.basename(path), exc_info=True)

    try:
        response = send_file(serve_path, as_attachment=True, download_name=display_name,
                             conditional=not cleanup_paths)
    except Exception:
        cleanup_burn_files()
        raise
    if str(burn_after_read).strip() == "1":
        response.headers["Cache-Control"] = "no-store, private"

        # Let Werkzeug wrap the file iterator and invoke Response.close on
        # normal completion, disconnect, or early WSGI iterator close.
        response.direct_passthrough = False
        response.call_on_close(cleanup_burn_files)

    return response
