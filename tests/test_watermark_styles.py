import pathlib

import pytest

from services.watermark_styles import (
    WatermarkStyleConfigError,
    get_default_style_id,
    get_style,
    is_style_enabled,
    list_enabled_styles,
    load_watermark_styles,
)


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_load_default_watermark_style_config():
    config_path = PROJECT_ROOT / "config" / "watermark_styles.toml"
    config = load_watermark_styles(str(config_path))

    assert get_default_style_id(config) == 1
    assert len(list_enabled_styles(config)) >= 1
    assert is_style_enabled(config, 1)
    assert get_style(config, 4)["background"] == "frosted"


def test_load_default_watermark_style_config_with_relative_path():
    config = load_watermark_styles("./config/watermark_styles.toml")
    assert get_default_style_id(config) == 1
    assert len(list_enabled_styles(config)) >= 1


def test_watermark_style_config_requires_styles(tmp_path):
    config_file = tmp_path / "watermark_styles.toml"
    config_file.write_text("[global]\ndefault_style_id=1\n", encoding="utf-8")

    with pytest.raises(WatermarkStyleConfigError):
        load_watermark_styles(str(config_file))


def test_watermark_style_default_falls_back_to_first_enabled(tmp_path):
    config_file = tmp_path / "watermark_styles.toml"
    config_file.write_text(
        """
[global]
default_style_id = 99

[styles.5]
enabled = true
label_zh = "新样式"
label_en = "New Style"
preview_image = "images/custom.png"
layout = "split_lr"
background = "white"
""".strip(),
        encoding="utf-8",
    )

    config = load_watermark_styles(str(config_file))
    assert get_default_style_id(config) == 5
    assert len(list_enabled_styles(config)) == 1
