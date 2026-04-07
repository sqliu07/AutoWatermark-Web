import os
import tempfile

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


def _dir_is_writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".writable_probe")
        with open(probe, "w", encoding="utf-8") as fp:
            fp.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _db_path_is_writable(db_path: str) -> bool:
    db_dir = os.path.dirname(db_path) or "."
    if not _dir_is_writable(db_dir):
        return False

    if not os.path.exists(db_path):
        return True

    try:
        with open(db_path, "a", encoding="utf-8"):
            return True
    except OSError:
        return False


def _resolve_runtime_paths(app, logger) -> None:
    upload_folder = app.config["UPLOAD_FOLDER"]
    if not _dir_is_writable(upload_folder):
        fallback_upload = os.path.join(tempfile.gettempdir(), "autowatermark", "upload")
        os.makedirs(fallback_upload, exist_ok=True)
        logger.warning(
            "UPLOAD_FOLDER '%s' is not writable, fallback to '%s'",
            upload_folder,
            fallback_upload,
        )
        upload_folder = fallback_upload
    app.config["UPLOAD_FOLDER"] = upload_folder

    requested_state_db = app.config.get("STATE_DB_PATH")
    if not requested_state_db:
        requested_state_db = os.path.join(upload_folder, AppConstants.STATE_DB_FILENAME)

    if not _db_path_is_writable(requested_state_db):
        fallback_state_db = os.path.join(
            tempfile.gettempdir(), "autowatermark", AppConstants.STATE_DB_FILENAME
        )
        if not _db_path_is_writable(fallback_state_db):
            raise RuntimeError(
                f"STATE_DB_PATH '{requested_state_db}' is not writable and fallback '{fallback_state_db}' failed"
            )
        logger.warning(
            "STATE_DB_PATH '%s' is not writable, fallback to '%s'",
            requested_state_db,
            fallback_state_db,
        )
        requested_state_db = fallback_state_db

    app.config["STATE_DB_PATH"] = requested_state_db


def create_app(config_overrides=None):
    app = Flask(__name__, static_url_path="/static", static_folder="./static")

    logger = get_logger("autowatermark.app")
    app.logger.handlers.clear()
    for handler in logger.handlers:
        app.logger.addHandler(handler)
    app.logger.setLevel(logger.level)
    app.logger.propagate = False

    app.config.from_mapping(
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", AppConstants.UPLOAD_FOLDER),
        STATE_DB_PATH=None,
        ALLOWED_EXTENSIONS=AppConstants.ALLOWED_EXTENSIONS,
        MAX_CONTENT_LENGTH=AppConstants.MAX_CONTENT_LENGTH,
        START_BACKGROUND_CLEANER=True,
        WATERMARK_STYLE_CONFIG_PATH=CommonConstants.WATERMARK_STYLE_CONFIG_PATH,
    )

    if config_overrides:
        app.config.update(config_overrides)

    _resolve_runtime_paths(app, logger)

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
