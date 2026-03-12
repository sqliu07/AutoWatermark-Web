from flask import jsonify, render_template, request
from flask_limiter.errors import RateLimitExceeded

from services.i18n import normalize_lang


def register_error_handlers(app):
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_error(e):
        lang = normalize_lang(request.args.get("lang", "zh"))
        msg = "请求过于频繁，请稍后再试。" if lang == "zh" else "Too many requests, please try again later."
        return jsonify(error=msg), 429

    @app.errorhandler(404)
    def not_found_error(error):
        lang = normalize_lang(request.args.get("lang", "zh"))
        translations = app.extensions.get("translations", {})
        return render_template("image_deleted.html", lang=lang, translations=translations), 404
