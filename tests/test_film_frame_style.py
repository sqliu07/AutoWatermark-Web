from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import piexif
from PIL import Image

import process as process_module
from constants import CommonConstants
from imaging import generate_watermark_image
from imaging.renderer_film_frame import FilmFrameRenderer
from media.ultrahdr import inject_xmp, parse_gcontainer_items_from_xmp
from services.watermark_styles import get_style, load_watermark_styles
from process_result import ProcessResult


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

    def fake_caption_group(self, context, framed_photo, metrics):
        captured["framed_size"] = framed_photo.size
        captured["metrics"] = dict(metrics)
        return Image.new("RGBA", (120, 80), (255, 255, 255, 0))

    monkeypatch.setattr(FilmFrameRenderer, "_create_caption_group", fake_caption_group)

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
    fc = style["frame"]
    expected_logo_height = max(24, int(round(framed_height * fc["logo_height_ratio_portrait"])))
    expected_font_size = max(12, int(round(framed_width * fc["font_size_ratio_portrait"])))
    expected_line_gap = max(10, int(round(framed_width * fc["line_gap_ratio_portrait"])))
    landscape_logo_height = max(24, int(round(framed_height * fc["logo_height_ratio"])))
    landscape_font_size = max(12, int(round(framed_width * fc["font_size_ratio"])))
    landscape_line_gap = max(10, int(round(framed_width * fc["line_gap_ratio"])))

    assert metrics["logo_height"] == expected_logo_height
    assert metrics["font_start_size"] == expected_font_size
    assert metrics["line_gap"] == expected_line_gap
    assert metrics["logo_height"] != landscape_logo_height
    assert metrics["font_start_size"] != landscape_font_size
    assert metrics["line_gap"] != landscape_line_gap
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

    assert result.success is True
    assert output_path.exists()
    assert logo_calls


def test_process_image_preserves_exif_when_orientation_is_reset(tmp_path, monkeypatch):
    image_path = tmp_path / "portrait.jpg"
    output_path = tmp_path / "portrait_watermark.jpg"
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"EOS R6",
            piexif.ImageIFD.Orientation: 6,
        },
        "Exif": {
            piexif.ExifIFD.LensModel: b"RF50mm F1.8 STM",
            piexif.ExifIFD.FocalLengthIn35mmFilm: 50,
            piexif.ExifIFD.FNumber: (18, 10),
            piexif.ExifIFD.ExposureTime: (1, 125),
            piexif.ExifIFD.ISOSpeedRatings: 200,
            piexif.ExifIFD.DateTimeOriginal: b"2026:03:07 12:00:00",
        },
    }
    Image.new("RGB", (48, 64), "#ffffff").save(image_path, exif=piexif.dump(exif_dict))

    style_config = load_watermark_styles(str(PROJECT_ROOT / "config" / "watermark_styles.toml"))

    monkeypatch.setattr(process_module, "prepare_motion_photo", lambda _: None)
    monkeypatch.setattr(process_module, "split_ultrahdr", lambda _: None)
    monkeypatch.setattr(process_module, "find_logo", lambda *_args, **_kwargs: str(LOGO_PATH))
    monkeypatch.setattr(
        process_module,
        "generate_watermark_image",
        lambda image, logo_path, *args, **kwargs: image.copy(),
    )

    result = process_module.process_image(
        str(image_path),
        watermark_type=1,
        image_quality=85,
        style_config=style_config,
    )

    assert result.success is True
    assert output_path.exists()


def test_process_image_uses_exiftool_xiaomi_model_fallback(tmp_path, monkeypatch):
    image_path = tmp_path / "xiaomi-private-tags.jpg"
    output_path = tmp_path / "xiaomi-private-tags_watermark.jpg"
    exif_dict = {
        "0th": {
            piexif.ImageIFD.ImageWidth: 64,
            piexif.ImageIFD.ImageLength: 48,
        },
        "Exif": {
            piexif.ExifIFD.FocalLengthIn35mmFilm: 23,
            piexif.ExifIFD.FNumber: (17, 10),
            piexif.ExifIFD.ExposureTime: (1, 3395),
            piexif.ExifIFD.ISOSpeedRatings: 64,
        },
    }
    Image.new("RGB", (64, 48), "#ffffff").save(image_path, exif=piexif.dump(exif_dict))

    style_config = load_watermark_styles(str(PROJECT_ROOT / "config" / "watermark_styles.toml"))
    captured = {}

    monkeypatch.setattr(process_module, "prepare_motion_photo", lambda _: None)
    monkeypatch.setattr(process_module, "split_ultrahdr", lambda _: None)
    monkeypatch.setattr(process_module, "find_logo", lambda *_args, **_kwargs: str(PROJECT_ROOT / "logos" / "xiaomi.png"))
    monkeypatch.setattr(
        process_module,
        "get_exif_data_with_exiftool",
        lambda *_args, **_kwargs: {
            "manufacturer": "Xiaomi",
            "camera_model": "REDMI K90 Pro Max",
            "camera_info": "Xiaomi\nREDMI K90 Pro Max",
            "shooting_info": "23mm  ƒ/1.7  1/3395s  ISO64\nUnknown Date",
        },
        raising=False,
    )

    def fake_generate_watermark_image(image, logo_path, camera_info, shooting_info, *args, **kwargs):
        captured["logo_path"] = logo_path
        captured["camera_info"] = camera_info
        captured["shooting_info"] = shooting_info
        return image.copy()

    monkeypatch.setattr(process_module, "generate_watermark_image", fake_generate_watermark_image)

    result = process_module.process_image(
        str(image_path),
        watermark_type=1,
        image_quality=85,
        style_config=style_config,
    )

    assert result.success is True
    assert output_path.exists()
    assert captured["camera_info"] == ["Xiaomi", "REDMI K90 Pro Max"]
    assert captured["shooting_info"] == ["23mm  ƒ/1.7  1/3395s  ISO64", "Unknown Date"]


def test_process_image_synthesizes_primary_xmp_for_gainmap_only_ultrahdr(tmp_path, monkeypatch):
    image_path = tmp_path / "gainmap-only-ultrahdr.jpg"
    output_path = tmp_path / "gainmap-only-ultrahdr_watermark.jpg"
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"EOS R6",
        },
        "Exif": {
            piexif.ExifIFD.LensModel: b"RF50mm F1.8 STM",
            piexif.ExifIFD.FocalLengthIn35mmFilm: 50,
            piexif.ExifIFD.FNumber: (18, 10),
            piexif.ExifIFD.ExposureTime: (1, 125),
            piexif.ExifIFD.ISOSpeedRatings: 200,
            piexif.ExifIFD.DateTimeOriginal: b"2026:03:07 12:00:00",
        },
    }
    Image.new("RGB", (64, 48), "#ffffff").save(image_path, exif=piexif.dump(exif_dict))
    primary_jpeg = image_path.read_bytes()
    gainmap_xmp = b'''<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/"
      hdrgm:Version="1.0"
      hdrgm:GainMapMin="0"
      hdrgm:GainMapMax="2"
      hdrgm:Gamma="1" />
  </rdf:RDF>
</x:xmpmeta>'''
    gainmap_buffer = BytesIO()
    Image.new("L", (2, 2), 128).save(gainmap_buffer, format="JPEG")
    gainmap_jpeg = inject_xmp(gainmap_buffer.getvalue(), gainmap_xmp)

    style_config = load_watermark_styles(str(PROJECT_ROOT / "config" / "watermark_styles.toml"))

    monkeypatch.setattr(process_module, "prepare_motion_photo", lambda _: None)
    monkeypatch.setattr(
        process_module,
        "split_ultrahdr",
        lambda _: SimpleNamespace(
            primary_jpeg=primary_jpeg,
            gainmap_jpeg=gainmap_jpeg,
            primary_xmp=None,
            gainmap_xmp=gainmap_xmp,
        ),
    )
    monkeypatch.setattr(process_module, "find_logo", lambda *_args, **_kwargs: str(LOGO_PATH))
    monkeypatch.setattr(
        process_module,
        "generate_watermark_image",
        lambda image, logo_path, *args, **kwargs: (image.copy(), {"content_box": (0, 0, image.width, image.height)}),
    )

    result = process_module.process_image(
        str(image_path),
        watermark_type=1,
        image_quality=85,
        style_config=style_config,
    )

    assert result.success is True
    assert output_path.exists()
    output_bytes = output_path.read_bytes()
    primary_xmp_start = output_bytes.index(b"<x:xmpmeta")
    primary_xmp_end = output_bytes.index(b"</x:xmpmeta>", primary_xmp_start) + len(b"</x:xmpmeta>")
    primary_xmp = output_bytes[primary_xmp_start:primary_xmp_end]

    items = parse_gcontainer_items_from_xmp(primary_xmp)
    assert [item["semantic"] for item in items] == ["Primary", "GainMap"]
    assert items[0]["length"] is not None
    assert items[1]["length"] == len(gainmap_jpeg)
    assert output_bytes.endswith(gainmap_jpeg)
