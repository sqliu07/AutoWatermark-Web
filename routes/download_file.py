import os
import tempfile

from flask import Blueprint, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from routes._utils import is_browser_request
from services.download_token import verify_token
from services.i18n import get_error_message, normalize_lang

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

    if not verify_token(filename, token, expires, action="download", burn=str(burn_after_read).strip()):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("link_expired", lang)), 403

    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(file_path):
        if is_browser:
            return render_template("image_deleted.html"), 404
        return jsonify(error=get_error_message("file_not_found", lang)), 404

    serve_path = file_path
    if str(burn_after_read).strip() == "1":
        suffix = os.path.splitext(filename)[1]
        fd, burn_path = tempfile.mkstemp(prefix=".burn_", suffix=suffix, dir=current_app.config["UPLOAD_FOLDER"])
        os.close(fd)
        try:
            os.replace(file_path, burn_path)
        except OSError:
            try:
                os.remove(burn_path)
            except OSError:
                pass
            if is_browser:
                return render_template("image_deleted.html"), 404
            return jsonify(error=get_error_message("file_not_found", lang)), 404
        serve_path = burn_path

    response = send_file(serve_path, as_attachment=True, download_name=filename)
    if str(burn_after_read).strip() == "1":
        response.headers["Cache-Control"] = "no-store, private"

        @response.call_on_close
        def _cleanup_burn_file():
            try:
                os.remove(serve_path)
            except OSError:
                pass

    return response
