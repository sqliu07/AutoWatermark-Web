import os

from app_factory import create_app

app = create_app()

if __name__ == "__main__":
    is_production = os.environ.get("FLASK_ENV") == "production"
    host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"

    if is_production:
        app.logger.info("请使用 gunicorn 启动：gunicorn -w 1 -b 0.0.0.0:5000 app:app")
    else:
        app.run(host=host, port=port, debug=debug)
