from pathlib import Path

import piexif
from PIL import Image

import image_utils as image_utils_module
import process as process_module
from constants import CommonConstants
from image_utils import generate_watermark_image
from services.watermark_styles import get_style, load_watermark_styles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = PROJECT_ROOT / "logos" / "canon.png"


def test_generate_film_frame_style_creates_film_frame_layout():
    config = load_watermark_styles(str(PROJECT_ROOT / "config" / "watermark_styles.toml"))
    style = get_style(config, 5)

    source = Image.new("RGB", (800, 600), "#4a7391")
    rendered, metadata = generate_watermark_image(
        source,
        logo_path=str(LOGO_PATH),
        camera_info=["Summicron 35mm f/2", "Fujifilm X100V"],
        shooting_info=["35mm  ƒ/2  1/125s  ISO200", "2026.03.07 12:00:00"],
        font_path_thin=CommonConstants.GLOBAL_FONT_PATH_LIGHT,
        font_path_bold=CommonConstants.GLOBAL_FONT_PATH_BOLD,
        watermark_type=5,
        font_path_regular=CommonConstants.GLOBAL_FONT_PATH_MONO,
        font_path_symbol=CommonConstants.GLOBAL_FONT_PATH_REGULAR,
        return_metadata=True,
        style_config=config,
        style=style,
    )

    assert rendered.width > source.width
    assert rendered.height > source.height
    assert rendered.width == rendered.height
    assert rendered.getpixel((10, 10)) == (236, 236, 236)

    x0, y0, x1, y1 = metadata["content_box"]
    assert (x1 - x0, y1 - y0) == source.size
    assert rendered.getpixel((x0 - 1, y0 - 1)) == (0, 0, 0)
    assert rendered.getbbox() is not None


def test_generate_film_frame_style_portrait_uses_portrait_overrides(monkeypatch):
    config = load_watermark_styles(str(PROJECT_ROOT / "config" / "watermark_styles.toml"))
    style = get_style(config, 5)
    captured = {}

    def fake_caption_group(
        camera_info,
        shooting_info,
        font_path_regular,
        framed_photo,
        logo_path,
        metrics,
        font_path_symbol,
    ):
        captured["framed_size"] = framed_photo.size
        captured["metrics"] = dict(metrics)
        return Image.new("RGBA", (120, 80), (255, 255, 255, 0))

    monkeypatch.setattr(image_utils_module, "_create_film_frame_caption_group", fake_caption_group)

    source = Image.new("RGB", (600, 900), "#4a7391")
    rendered = generate_watermark_image(
        source,
        logo_path=str(LOGO_PATH),
        camera_info=["Summicron 35mm f/2", "Fujifilm X100V"],
        shooting_info=["35mm  ƒ/2  1/125s  ISO200", "2026.03.07 12:00:00"],
        font_path_thin=CommonConstants.GLOBAL_FONT_PATH_LIGHT,
        font_path_bold=CommonConstants.GLOBAL_FONT_PATH_BOLD,
        watermark_type=5,
        font_path_regular=CommonConstants.GLOBAL_FONT_PATH_MONO,
        font_path_symbol=CommonConstants.GLOBAL_FONT_PATH_REGULAR,
        style_config=config,
        style=style,
    )

    framed_width, framed_height = captured["framed_size"]
    metrics = captured["metrics"]
    expected_logo_height = max(24, int(round(framed_height * style["frame_logo_height_ratio_portrait"])))
    expected_font_size = max(12, int(round(framed_width * style["frame_font_size_ratio_portrait"])))
    landscape_logo_height = max(24, int(round(framed_height * style["frame_logo_height_ratio"])))
    landscape_font_size = max(12, int(round(framed_width * style["frame_font_size_ratio"])))

    assert metrics["logo_height"] == expected_logo_height
    assert metrics["font_start_size"] == expected_font_size
    assert metrics["logo_height"] != landscape_logo_height
    assert metrics["font_start_size"] != landscape_font_size
    assert rendered.height > source.height
    assert rendered.width > source.width
    assert rendered.width == rendered.height


def test_process_image_film_frame_style_uses_logo(tmp_path, monkeypatch):
    image_path = tmp_path / "source.jpg"
    output_path = tmp_path / "source_watermark.jpg"
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Unknown Brand",
            piexif.ImageIFD.Model: b"Model X",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: b"2026:03:07 12:00:00",
        },
    }

    Image.new("RGB", (64, 48), "#ffffff").save(image_path, exif=piexif.dump(exif_dict))
    style_config = load_watermark_styles(str(PROJECT_ROOT / "config" / "watermark_styles.toml"))
    logo_calls = []

    monkeypatch.setattr(process_module, "prepare_motion_photo", lambda _: None)
    monkeypatch.setattr(process_module, "split_ultrahdr", lambda _: None)
    monkeypatch.setattr(process_module, "get_manufacturer", lambda *_args, **_kwargs: "Unknown Brand")
    monkeypatch.setattr(process_module, "get_camera_model", lambda *_args, **_kwargs: "Model X")
    monkeypatch.setattr(process_module, "find_logo", lambda *_args, **_kwargs: logo_calls.append(True) or str(LOGO_PATH))
    monkeypatch.setattr(
        process_module,
        "get_exif_data",
        lambda *_args, **_kwargs: ("Summicron 35mm f/2\nModel X", "35mm  ƒ/2  1/125s  ISO200\n2026.03.07 12:00:00"),
    )
    monkeypatch.setattr(
        process_module,
        "generate_watermark_image",
        lambda image, logo_path, *args, **kwargs: image.copy(),
    )

    result = process_module.process_image(
        str(image_path),
        watermark_type=5,
        image_quality=85,
        style_config=style_config,
    )

    assert result is True
    assert output_path.exists()
    assert logo_calls
