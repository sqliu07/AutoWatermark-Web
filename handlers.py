from flask import current_app, jsonify, redirect, request
from flask_limiter.errors import RateLimitExceeded
from werkzeug.exceptions import HTTPException

from routes._utils import is_browser_request
from services.i18n import get_error_message, normalize_lang


def register_error_handlers(app):
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_error(e):
        lang = normalize_lang(request.args.get("lang", "zh"))
        return jsonify(error=get_error_message("rate_limit_exceeded", lang)), 429

    @app.errorhandler(404)
    def not_found_error(error):
        if is_browser_request():
            return redirect("/")
        lang = normalize_lang(request.args.get("lang", "zh"))
        return jsonify(error=get_error_message("file_not_found", lang)), 404

    @app.errorhandler(500)
    def internal_error(error):
        current_app.logger.exception("Internal server error")
        lang = normalize_lang(request.args.get("lang", "zh"))
        return jsonify(error=get_error_message("unexpected_error", lang)), 500

    @app.errorhandler(Exception)
    def unhandled_error(error):
        if isinstance(error, HTTPException):
            return error
        current_app.logger.exception("Unhandled exception in request")
        lang = normalize_lang(request.args.get("lang", "zh"))
        return jsonify(error=get_error_message("unexpected_error", lang)), 500
