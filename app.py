import os

from app_factory import create_app

app = create_app()

if __name__ == "__main__":
    is_production = os.environ.get("FLASK_ENV") == "production"

    if is_production:
        app.logger.info("请使用 gunicorn 启动：gunicorn -w 4 -b 0.0.0.0:5000 app:app")
    else:
        app.run(host="0.0.0.0", port=5000, debug=True)
