from flask import Blueprint, render_template, request, current_app

from services.i18n import normalize_lang

bp = Blueprint("index", __name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/not_found")
def not_found_page():
    lang = normalize_lang(request.args.get("lang", "zh"))
    translations = current_app.extensions.get("translations", {})
    return render_template("image_deleted.html", lang=lang, translations=translations), 404
