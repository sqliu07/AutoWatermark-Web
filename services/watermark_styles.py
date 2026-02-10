from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


_DEFAULT_GLOBAL = {
    "default_style_id": 1,
    "footer_ratio_landscape": 0.09,
    "footer_ratio_portrait": 0.08,
    "font_size_ratio": 0.22,
    "portrait_font_scale": 0.75,
    "min_font_size": 20,
}

_DEFAULT_STYLE = {
    "enabled": True,
    "display_code": "",
    "label_zh": "",
    "label_en": "",
    "preview_image": "",
    "layout": "split_lr",
    "background": "white",
    "border_top_ratio": 0.0,
    "border_left_ratio": 0.0,
    "padding_x_mode": "border_left",
    "padding_x_ratio": 0.0,
    "right_divider_line": True,
    "center_logo_ratio": 0.55,
    "center_gap_ratio": 0.15,
    "text_color_mode": "black",
    "position_mode": "footer_center",
    "bottom_offset_portrait_divisor": 4,
    "bottom_offset_landscape_divisor": 6,
    "supports_motion": True,
    "supports_ultrahdr": True,
}

_ALLOWED_LAYOUTS = {"split_lr", "center_stack"}
_ALLOWED_BACKGROUNDS = {"white", "frosted"}
_ALLOWED_PADDING_MODES = {"border_left", "footer_ratio"}
_ALLOWED_TEXT_COLOR_MODES = {"black", "auto_contrast"}
_ALLOWED_POSITION_MODES = {"footer_center", "bottom_offset"}


class WatermarkStyleConfigError(ValueError):
    """Raised when watermark style configuration is invalid."""


def _ensure_type(value: Any, expected_type: type, field_name: str):
    if not isinstance(value, expected_type):
        raise WatermarkStyleConfigError(f"Field '{field_name}' has invalid type: {type(value).__name__}")
    return value


def _as_bool(value: Any, field_name: str) -> bool:
    return bool(_ensure_type(value, bool, field_name))


def _as_str(value: Any, field_name: str) -> str:
    return str(_ensure_type(value, str, field_name)).strip()


def _as_float(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise WatermarkStyleConfigError(f"Field '{field_name}' must be a number")
    return float(value)


def _as_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int):
        raise WatermarkStyleConfigError(f"Field '{field_name}' must be an integer")
    return value


def _normalize_global(raw_global: Dict[str, Any]) -> Dict[str, Any]:
    global_config = dict(_DEFAULT_GLOBAL)
    global_config.update(raw_global)

    normalized = {
        "default_style_id": _as_int(global_config["default_style_id"], "global.default_style_id"),
        "footer_ratio_landscape": _as_float(global_config["footer_ratio_landscape"], "global.footer_ratio_landscape"),
        "footer_ratio_portrait": _as_float(global_config["footer_ratio_portrait"], "global.footer_ratio_portrait"),
        "font_size_ratio": _as_float(global_config["font_size_ratio"], "global.font_size_ratio"),
        "portrait_font_scale": _as_float(global_config["portrait_font_scale"], "global.portrait_font_scale"),
        "min_font_size": _as_int(global_config["min_font_size"], "global.min_font_size"),
    }

    if normalized["min_font_size"] < 1:
        raise WatermarkStyleConfigError("global.min_font_size must be >= 1")

    return normalized


def _normalize_style(style_id: int, raw_style: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_style, dict):
        raise WatermarkStyleConfigError(f"styles.{style_id} must be a table")

    style = dict(_DEFAULT_STYLE)
    style.update(raw_style)

    normalized = {
        "style_id": style_id,
        "enabled": _as_bool(style["enabled"], f"styles.{style_id}.enabled"),
        "display_code": _as_str(style["display_code"], f"styles.{style_id}.display_code"),
        "label_zh": _as_str(style["label_zh"], f"styles.{style_id}.label_zh"),
        "label_en": _as_str(style["label_en"], f"styles.{style_id}.label_en"),
        "preview_image": _as_str(style["preview_image"], f"styles.{style_id}.preview_image"),
        "layout": _as_str(style["layout"], f"styles.{style_id}.layout"),
        "background": _as_str(style["background"], f"styles.{style_id}.background"),
        "border_top_ratio": _as_float(style["border_top_ratio"], f"styles.{style_id}.border_top_ratio"),
        "border_left_ratio": _as_float(style["border_left_ratio"], f"styles.{style_id}.border_left_ratio"),
        "padding_x_mode": _as_str(style["padding_x_mode"], f"styles.{style_id}.padding_x_mode"),
        "padding_x_ratio": _as_float(style["padding_x_ratio"], f"styles.{style_id}.padding_x_ratio"),
        "right_divider_line": _as_bool(style["right_divider_line"], f"styles.{style_id}.right_divider_line"),
        "center_logo_ratio": _as_float(style["center_logo_ratio"], f"styles.{style_id}.center_logo_ratio"),
        "center_gap_ratio": _as_float(style["center_gap_ratio"], f"styles.{style_id}.center_gap_ratio"),
        "text_color_mode": _as_str(style["text_color_mode"], f"styles.{style_id}.text_color_mode"),
        "position_mode": _as_str(style["position_mode"], f"styles.{style_id}.position_mode"),
        "bottom_offset_portrait_divisor": _as_int(
            style["bottom_offset_portrait_divisor"], f"styles.{style_id}.bottom_offset_portrait_divisor"
        ),
        "bottom_offset_landscape_divisor": _as_int(
            style["bottom_offset_landscape_divisor"], f"styles.{style_id}.bottom_offset_landscape_divisor"
        ),
        "supports_motion": _as_bool(style["supports_motion"], f"styles.{style_id}.supports_motion"),
        "supports_ultrahdr": _as_bool(style["supports_ultrahdr"], f"styles.{style_id}.supports_ultrahdr"),
    }

    if normalized["layout"] not in _ALLOWED_LAYOUTS:
        raise WatermarkStyleConfigError(f"styles.{style_id}.layout must be one of {_ALLOWED_LAYOUTS}")
    if normalized["background"] not in _ALLOWED_BACKGROUNDS:
        raise WatermarkStyleConfigError(f"styles.{style_id}.background must be one of {_ALLOWED_BACKGROUNDS}")
    if normalized["padding_x_mode"] not in _ALLOWED_PADDING_MODES:
        raise WatermarkStyleConfigError(f"styles.{style_id}.padding_x_mode must be one of {_ALLOWED_PADDING_MODES}")
    if normalized["text_color_mode"] not in _ALLOWED_TEXT_COLOR_MODES:
        raise WatermarkStyleConfigError(f"styles.{style_id}.text_color_mode must be one of {_ALLOWED_TEXT_COLOR_MODES}")
    if normalized["position_mode"] not in _ALLOWED_POSITION_MODES:
        raise WatermarkStyleConfigError(f"styles.{style_id}.position_mode must be one of {_ALLOWED_POSITION_MODES}")

    if normalized["bottom_offset_portrait_divisor"] <= 0:
        raise WatermarkStyleConfigError(f"styles.{style_id}.bottom_offset_portrait_divisor must be > 0")
    if normalized["bottom_offset_landscape_divisor"] <= 0:
        raise WatermarkStyleConfigError(f"styles.{style_id}.bottom_offset_landscape_divisor must be > 0")

    return normalized


def _parse_toml(path: Path) -> Dict[str, Any]:
    with path.open("rb") as fp:
        return tomllib.load(fp)


def _resolve_config_path(config_path: str) -> Path:
    path = Path(config_path)
    if path.exists() or path.is_absolute():
        return path

    project_root = Path(__file__).resolve().parents[1]
    candidate = (project_root / path).resolve()
    if candidate.exists():
        return candidate
    return path


def load_watermark_styles(config_path: str) -> Dict[str, Any]:
    path = _resolve_config_path(config_path)
    if not path.exists():
        raise WatermarkStyleConfigError(f"Watermark style config not found: {config_path}")

    raw = _parse_toml(path)
    raw_global = raw.get("global", {})
    raw_styles = raw.get("styles", {})

    if not isinstance(raw_styles, dict) or not raw_styles:
        raise WatermarkStyleConfigError("[styles] section is required and cannot be empty")

    global_config = _normalize_global(raw_global if isinstance(raw_global, dict) else {})

    styles: Dict[int, Dict[str, Any]] = {}
    for raw_style_id, raw_style in raw_styles.items():
        try:
            style_id = int(raw_style_id)
        except (TypeError, ValueError) as exc:
            raise WatermarkStyleConfigError(f"Invalid style id: {raw_style_id}") from exc
        styles[style_id] = _normalize_style(style_id, raw_style)

    enabled_styles = [style for _, style in sorted(styles.items()) if style["enabled"]]
    if not enabled_styles:
        raise WatermarkStyleConfigError("At least one watermark style must be enabled")

    default_style_id = global_config["default_style_id"]
    if default_style_id not in styles or not styles[default_style_id]["enabled"]:
        default_style_id = enabled_styles[0]["style_id"]

    return {
        "global": global_config,
        "styles": styles,
        "enabled_styles": enabled_styles,
        "default_style_id": default_style_id,
        "config_path": str(path),
    }


@lru_cache(maxsize=8)
def load_cached_watermark_styles(config_path: str) -> Dict[str, Any]:
    return load_watermark_styles(config_path)


def get_style(config: Dict[str, Any], style_id: int) -> Optional[Dict[str, Any]]:
    return config.get("styles", {}).get(style_id)


def is_style_enabled(config: Dict[str, Any], style_id: int) -> bool:
    style = get_style(config, style_id)
    return bool(style and style.get("enabled"))


def get_default_style_id(config: Dict[str, Any]) -> int:
    return int(config["default_style_id"])


def list_enabled_styles(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(config.get("enabled_styles", []))
