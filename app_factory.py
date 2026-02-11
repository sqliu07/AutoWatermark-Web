import os

from flask import Flask

from config.settings import AppConfig
from extensions import limiter
from handlers import register_error_handlers
from logging_utils import get_logger
from routes.download import bp as download_bp
from routes.index import bp as index_bp
from routes.upload import bp as upload_bp
from services.cleanup import start_background_cleaner
from services.i18n import load_translations
from services.state import AppState
from services.watermark_styles import load_cached_watermark_styles


def create_app(config: AppConfig = None):
    """Create and configure Flask application.

    Args:
        config: Application configuration. If None, loads from environment variables.

    Returns:
        Configured Flask application instance.
    """
    if config is None:
        config = AppConfig.from_env()

    app = Flask(__name__, static_url_path="/static", static_folder=str(config.static_folder))

    logger = get_logger("autowatermark.app")
    app.logger.handlers.clear()
    for handler in logger.handlers:
        app.logger.addHandler(handler)
    app.logger.setLevel(logger.level)
    app.logger.propagate = False

    # Store configuration in app.config for backward compatibility
    app.config["app_config"] = config
    app.config["UPLOAD_FOLDER"] = str(config.upload_folder)
    app.config["ALLOWED_EXTENSIONS"] = config.allowed_extensions
    app.config["MAX_CONTENT_LENGTH"] = config.max_content_length
    app.config["START_BACKGROUND_CLEANER"] = config.start_background_cleaner

    # Create upload directory if it doesn't exist
    os.makedirs(config.upload_folder, exist_ok=True)

    limiter.init_app(app)

    translations = load_translations(str(config.i18n_folder / "translations.json"), logger)
    watermark_styles = load_cached_watermark_styles(str(config.watermark_style_config_path))
    app.extensions["translations"] = translations
    app.extensions["watermark_styles"] = watermark_styles
    state = AppState()
    state.set_executor_config(config)
    app.extensions["state"] = state

    register_error_handlers(app)

    app.register_blueprint(index_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(download_bp)

    if config.start_background_cleaner:
        start_background_cleaner(app, app.extensions["state"], logger)

    return app
