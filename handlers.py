from flask import jsonify, redirect, request
from flask_limiter.errors import RateLimitExceeded

from services.i18n import get_error_message, normalize_lang


def register_error_handlers(app):
    def _is_browser_request() -> bool:
        return "text/html" in request.headers.get("Accept", "")

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_error(e):
        lang = normalize_lang(request.args.get("lang", "zh"))
        return jsonify(error=get_error_message("rate_limit_exceeded", lang)), 429

    @app.errorhandler(404)
    def not_found_error(error):
        if _is_browser_request():
            return redirect("/")
        lang = normalize_lang(request.args.get("lang", "zh"))
        return jsonify(error=get_error_message("file_not_found", lang)), 404
