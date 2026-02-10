from flask import Blueprint, render_template, request, current_app

from services.i18n import normalize_lang
from services.watermark_styles import get_default_style_id, list_enabled_styles

bp = Blueprint("index", __name__)


@bp.route("/")
def index():
    style_config = current_app.extensions.get("watermark_styles", {})
    watermark_styles = list_enabled_styles(style_config)
    default_style_id = get_default_style_id(style_config) if watermark_styles else None
    return render_template(
        "index.html",
        watermark_styles=watermark_styles,
        default_style_id=default_style_id,
    )


@bp.route("/not_found")
def not_found_page():
    lang = normalize_lang(request.args.get("lang", "zh"))
    translations = current_app.extensions.get("translations", {})
    return render_template("image_deleted.html", lang=lang, translations=translations), 404
