import os

from flask import Flask

from constants import AppConstants
from extensions import limiter
from handlers import register_error_handlers
from logging_utils import get_logger
from routes.download import bp as download_bp
from routes.index import bp as index_bp
from routes.upload import bp as upload_bp
from services.cleanup import start_background_cleaner
from services.i18n import load_translations
from services.state import AppState


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
        ALLOWED_EXTENSIONS=AppConstants.ALLOWED_EXTENSIONS,
        MAX_CONTENT_LENGTH=AppConstants.MAX_CONTENT_LENGTH,
        START_BACKGROUND_CLEANER=True,
    )

    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    limiter.init_app(app)

    translations = load_translations("static/i18n/translations.json", logger)
    app.extensions["translations"] = translations
    app.extensions["state"] = AppState()

    register_error_handlers(app)

    app.register_blueprint(index_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(download_bp)

    if app.config.get("START_BACKGROUND_CLEANER", True):
        start_background_cleaner(app, app.extensions["state"], logger)

    return app
