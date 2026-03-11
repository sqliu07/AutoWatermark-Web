from pathlib import Path

from PIL import Image

from scripts.generate_film_frame import DEFAULT_FONT_PATH, create_film_frame


def test_create_film_frame_generates_larger_composition(tmp_path):
    source_path = tmp_path / "source.jpg"
    output_path = tmp_path / "rendered.jpg"

    source = Image.new("RGB", (640, 480), "#4a7391")
    source.save(source_path, quality=95)

    create_film_frame(
        input_path=str(source_path),
        output_path=str(output_path),
        caption="Kodak Ultra Max 400",
        stamp_text="'26 3 7",
        font_path=str(DEFAULT_FONT_PATH),
    )

    assert output_path.exists()

    with Image.open(output_path) as rendered:
        assert rendered.width > 640
        assert rendered.height > 480
        assert rendered.getpixel((10, 10)) == (236, 236, 236)
