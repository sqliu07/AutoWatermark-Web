import os

from flask import Blueprint, jsonify, current_app, send_from_directory

from services.watermark_styles import get_default_style_id, list_enabled_styles

bp = Blueprint("index", __name__)


@bp.route("/api/styles")
def api_styles():
    """返回启用的水印样式列表和默认样式 ID。"""
    style_config = current_app.extensions.get("watermark_styles", {})
    styles = list_enabled_styles(style_config)
    default_id = get_default_style_id(style_config) if styles else None

    return jsonify({
        "styles": [
            {
                "style_id": s["style_id"],
                "label_zh": s.get("label_zh", f"样式 {s['style_id']}"),
                "label_en": s.get("label_en", f"Style {s['style_id']}"),
                "display_code": s.get("display_code", ""),
                "layout": s.get("layout", ""),
                "preview_image": f"/static/{s['preview_image']}" if s.get("preview_image") else None,
            }
            for s in styles
        ],
        "default_style_id": default_id,
    })


@bp.route("/")
def index():
    """SPA 入口：返回 Vue 构建产物的 index.html。"""
    dist_dir = os.path.join(current_app.static_folder, "dist")
    return send_from_directory(dist_dir, "index.html")
