import os

from flask import Flask, send_from_directory

from constants import AppConstants, CommonConstants
from extensions import limiter
from handlers import register_error_handlers
from logging_utils import get_logger
from routes.download import bp as download_bp
from routes.index import bp as index_bp
from routes.upload import bp as upload_bp
from services.cleanup import start_background_cleaner
from services.download_token import ensure_secret_configured
from services.state import AppState
from services.watermark_styles import load_cached_watermark_styles


def create_app(config_overrides=None):
    app = Flask(__name__, static_url_path="/static", static_folder="./static")

    logger = get_logger("autowatermark.app")
    app.logger.handlers.clear()
    for handler in logger.handlers:
        app.logger.addHandler(handler)
    app.logger.setLevel(logger.level)
    app.logger.propagate = False

    app.config.from_mapping(
        UPLOAD_FOLDER=AppConstants.UPLOAD_FOLDER,
        STATE_DB_PATH=None,
        ALLOWED_EXTENSIONS=AppConstants.ALLOWED_EXTENSIONS,
        MAX_CONTENT_LENGTH=AppConstants.MAX_CONTENT_LENGTH,
        START_BACKGROUND_CLEANER=True,
        WATERMARK_STYLE_CONFIG_PATH=CommonConstants.WATERMARK_STYLE_CONFIG_PATH,
    )

    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    if not app.config.get("STATE_DB_PATH"):
        app.config["STATE_DB_PATH"] = os.path.join(
            app.config["UPLOAD_FOLDER"], AppConstants.STATE_DB_FILENAME
        )

    ensure_secret_configured()

    limiter.init_app(app)

    watermark_styles = load_cached_watermark_styles(app.config["WATERMARK_STYLE_CONFIG_PATH"])
    app.extensions["watermark_styles"] = watermark_styles
    app.extensions["state"] = AppState(app.config["STATE_DB_PATH"])

    register_error_handlers(app)

    @app.after_request
    def _set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Vue 构建产物的静态文件路由
    dist_dir = os.path.join(app.static_folder, "dist")

    @app.route("/assets/<path:filename>")
    def dist_assets(filename):
        return send_from_directory(os.path.join(dist_dir, "assets"), filename)

    app.register_blueprint(index_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(download_bp)

    if app.config.get("START_BACKGROUND_CLEANER", True):
        start_background_cleaner(app, app.extensions["state"], logger)

    return app
