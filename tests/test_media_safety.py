from unittest.mock import Mock

import pytest
from PIL import Image

import process
from errors import WatermarkError


def test_skinny_input_rejected_before_orientation(tmp_path, monkeypatch):
    path = tmp_path / 'skinny.png'
    Image.new('RGB', (60000, 10)).save(path)
    rotate = Mock(side_effect=AssertionError('decoded before validation'))
    monkeypatch.setattr(process, 'reset_image_orientation', rotate)
    state = process._ProcessingState(str(path), '', str(path), {}, {}, 1, 95, '')
    try:
        with pytest.raises(WatermarkError):
            process._load_image(state)
        rotate.assert_not_called()
    finally:
        process._cleanup(state)


def test_preview_survives_cleanup():
    state = process._ProcessingState('', '', '', {}, {}, 1, 95, '')
    state.new_image = Image.new('RGB', (2, 2), 'red')
    result = process._save_output(state, True, Mock())
    process._cleanup(state)
    try:
        assert result.preview_image.getpixel((0, 0)) == (255, 0, 0)
    finally:
        result.preview_image.close()


def test_detection_does_not_prepare_or_decode(tmp_path, monkeypatch):
    path = tmp_path / 'image.jpg'
    Image.new('RGB', (2, 2)).save(path)
    prepare = Mock(side_effect=AssertionError('heavy preparation'))
    monkeypatch.setattr(process, 'prepare_motion_photo', prepare)
    assert process.detect_image_features(str(path)) == {'is_hdr': False, 'is_motion': False}
    prepare.assert_not_called()


def test_allocations_checked_before_pillow(monkeypatch):
    from imaging.safety import new_image
    allocate = Mock(side_effect=AssertionError('large allocation'))
    monkeypatch.setattr(Image, 'new', allocate)
    with pytest.raises(WatermarkError):
        new_image('RGB', (70804, 70804))
    allocate.assert_not_called()


def test_film_square_expansion_rejected(monkeypatch):
    from types import SimpleNamespace
    from imaging.renderer_film_frame import FilmFrameRenderer
    from services.watermark_styles import load_watermark_styles, get_style
    from constants import CommonConstants
    style = get_style(load_watermark_styles(CommonConstants.WATERMARK_STYLE_CONFIG_PATH), 5)
    source = Image.new('RGB', (7000, 250))
    caption = Image.new('RGBA', (100, 50))
    monkeypatch.setattr(FilmFrameRenderer, '_create_caption_group', lambda *args: caption)
    try:
        with pytest.raises(WatermarkError):
            FilmFrameRenderer().render(SimpleNamespace(style=style, origin_image=source))
    finally:
        source.close()
        caption.close()


def test_untrusted_text_is_bounded_before_font_metrics(monkeypatch):
    from imaging.text_rendering import text_to_image
    from PIL import ImageFont
    font = Mock(side_effect=AssertionError('font metrics accessed'))
    monkeypatch.setattr(ImageFont, 'truetype', font)
    with pytest.raises(WatermarkError):
        text_to_image('x' * 4097, '', 20, 'black')
    font.assert_not_called()


def test_empty_motion_file_is_not_motion(tmp_path):
    from media.motion_photo import find_motion_video_start
    path = tmp_path / 'empty.jpg'
    path.touch()
    assert find_motion_video_start(path) is None


@pytest.mark.parametrize("payload", [
    b'<!DOCTYPE x [<!ENTITY a "expanded">]><x>&a;</x>',
    b'<!DOCTYPE x SYSTEM "file:///etc/passwd"><x/>',
    pytest.param('<!DOCTYPE x [<!ENTITY a "expanded">]><x>&a;</x>'.encode('utf-16le'), id='utf16-dtd'),
    pytest.param(b"x" * 65536, id="oversized-xmp"),
])
def test_xmp_rejects_dtd_and_oversized_metadata_before_xml_parser(monkeypatch, payload):
    from media import ultrahdr
    parser = Mock(side_effect=AssertionError("unsafe XML reached parser"))
    monkeypatch.setattr(ultrahdr.ET, "fromstring", parser)
    assert ultrahdr.parse_gcontainer_items_from_xmp(payload) is None
    parser.assert_not_called()
