import hashlib
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

import process
from constants import CommonConstants
from imaging import watermark
from media.ultrahdr import UltraHDRParts, inject_xmp, split_ultrahdr
from services.watermark_styles import get_style, load_watermark_styles


@pytest.fixture
def style_config():
    return load_watermark_styles(CommonConstants.WATERMARK_STYLE_CONFIG_PATH)


def render(source, style_config, style_id=1, **kwargs):
    return watermark.generate_watermark_image(
        source, str(Path(__file__).resolve().parents[1] / "logos" / "canon.png"),
        ["Lens 35mm", "Camera X"], ["35mm  f/2  1/125s  ISO200", "2026.11.01"],
        CommonConstants.GLOBAL_FONT_PATH_LIGHT, CommonConstants.GLOBAL_FONT_PATH_BOLD,
        watermark_type=style_id, font_path_regular=CommonConstants.GLOBAL_FONT_PATH_MONO,
        font_path_symbol=CommonConstants.GLOBAL_FONT_PATH_REGULAR,
        style_config=style_config, **kwargs,
    )


@pytest.mark.parametrize("style_id,size,digest", [
    (1, (412, 334), "b5d1d8a210ac7cfb4bac88590d603068b21cccc18ba132f129cc1a4254227189"),
    (2, (400, 328), "5f60432b9aeaa7d61ba74e1e99570f903272d6fecb63427f8bd28186b503ca78"),
    (3, (412, 334), "7a4711849ecb548023cc2dfe269e0bd4a79c3ca0c9e6bf80e54691335072da04"),
    (4, (436, 346), "26f902e2d40cfd8f419c7b5e8e980860914f8eae9628b967adc67383fa3a8a98"),
    (5, (574, 574), "0ed4c0d0ed4bfc42360046a51dcd580416bf4607c14f8e2541da0d4b4b8f24a6"),
])
def test_existing_layout_pixels_are_unchanged(style_config, style_id, size, digest):
    with Image.new("RGB", (400, 300), "#4a7391") as source:
        rendered = render(source, style_config, style_id)
    try:
        assert rendered.size == size
        assert hashlib.sha256(rendered.tobytes()).hexdigest() == digest
    finally:
        rendered.close()


@pytest.mark.parametrize("style_id", [1, 3, 5])
def test_metadata_without_video_overlay_preserves_pixels_and_bounds(style_config, style_id):
    with Image.new("RGB", (400, 300), "#4a7391") as source:
        legacy, legacy_metadata = render(source, style_config, style_id, return_metadata=True)
        efficient, metadata = render(source, style_config, style_id, return_metadata=True, include_overlay=False)
    try:
        assert efficient.tobytes() == legacy.tobytes()
        assert metadata == {key: value for key, value in legacy_metadata.items() if key != "overlay_image"}
        assert "overlay_image" not in metadata
        box = metadata["content_box"]
        assert legacy_metadata["overlay_image"].getpixel((box[0], box[1])) == (0, 0, 0, 0)
        assert legacy.getpixel((box[0], box[1])) == (74, 115, 145)
    finally:
        legacy_metadata["overlay_image"].close()
        legacy.close()
        efficient.close()


@pytest.mark.parametrize("style_id", [3, 4, 5])
def test_non_split_layout_never_renders_unused_text_blocks(style_config, monkeypatch, style_id):
    unused = Mock(side_effect=AssertionError("unused split text was rendered"))
    monkeypatch.setattr(watermark, "create_text_block", unused)
    with Image.new("RGB", (400, 300), "#4a7391") as source:
        rendered = render(source, style_config, style_id)
    rendered.close()
    unused.assert_not_called()


@pytest.mark.parametrize("motion,hdr,preserve_motion,preserve_hdr,preview,style_id,want_metadata,want_overlay", [
    (False, True, True, True, False, 1, True, False),
    (True, False, True, True, False, 1, True, True),
    (True, True, False, True, False, 1, True, False),
    (False, True, True, False, False, 1, False, False),
    (True, True, True, True, True, 1, False, False),
    (True, True, True, True, False, 4, False, False),
])
def test_render_requests_only_required_media_allocations(
    style_config, monkeypatch, motion, hdr, preserve_motion, preserve_hdr,
    preview, style_id, want_metadata, want_overlay,
):
    state = process._ProcessingState("", "", "", style_config, get_style(style_config, style_id), style_id, 85, "xiaomi")
    state.camera_info = "Lens\nCamera"
    state.shooting_info = "35mm f/2\n2026.11.01"
    state.motion_session = object() if motion else None
    state.ultrahdr_parts = object() if hdr else None
    result = Image.new("RGB", (4, 4))

    def generate(*args, **kwargs):
        assert kwargs["return_metadata"] is want_metadata
        assert kwargs["include_overlay"] is want_overlay
        return (result, {"content_box": (0, 0, 4, 4)}) if want_metadata else result

    monkeypatch.setattr(process, "generate_watermark_image", generate)
    try:
        process._render_watermark(state, preserve_motion=preserve_motion, preserve_hdr=preserve_hdr, preview=preview)
        assert state.new_image is result
    finally:
        result.close()


@pytest.mark.parametrize("preview,style_id", [(False, 1), (True, 1), (False, 4)])
def test_stripped_or_preview_media_does_not_prepare_motion_workspace(style_config, monkeypatch, preview, style_id):
    state = process._ProcessingState("unused.jpg", "", "unused.jpg", style_config, get_style(style_config, style_id), style_id, 85, "xiaomi")
    prepare = Mock(side_effect=AssertionError("unused Motion workspace was prepared"))
    monkeypatch.setattr(process, "prepare_motion_photo", prepare)
    monkeypatch.setattr(process, "find_motion_video_start", lambda _: 10)
    process._detect_format(state, preserve_motion=False, preserve_hdr=False, preview=preview)
    assert state.motion_session is None
    assert state.ultrahdr_parts is None
    prepare.assert_not_called()


def test_preserving_hdr_while_stripping_motion_reads_only_still_prefix(style_config, tmp_path, monkeypatch):
    jpeg = BytesIO()
    with Image.new("RGB", (2, 2)) as image:
        image.save(jpeg, format="JPEG")
    still = inject_xmp(jpeg.getvalue(), b'<x hdrgm:Version="1.0"/>')
    video = b"video bytes that must not be copied for HDR parsing"
    path = tmp_path / "motion.jpg"
    path.write_bytes(still + video)
    state = process._ProcessingState(str(path), "", str(path), style_config, get_style(style_config, 1), 1, 85, "xiaomi")
    parts = UltraHDRParts(primary_jpeg=b"primary", gainmap_jpeg=b"gainmap", primary_xmp=b"xmp", gainmap_xmp=b"gainmap xmp", primary_len=7)
    parse = Mock(return_value=parts)
    prepare = Mock(side_effect=AssertionError("Motion workspace was prepared"))
    monkeypatch.setattr(process, "find_motion_video_start", lambda _: len(still))
    monkeypatch.setattr(process, "prepare_motion_photo", prepare)
    monkeypatch.setattr(process, "split_ultrahdr", parse)
    process._detect_format(state, preserve_motion=False, preserve_hdr=True)
    assert state.ultrahdr_parts is parts
    parse.assert_called_once_with(still)
    prepare.assert_not_called()


@pytest.mark.parametrize("preserve_hdr", [False, True])
def test_motion_stripping_preserves_real_still_pixels_and_exif(style_config, preserve_hdr):
    source = Path(__file__).parent / "fixtures" / "motion_photo.jpg"
    if not source.exists():
        pytest.skip("Real Motion Photo fixture is unavailable")
    prepared = process._ProcessingState(str(source), "", str(source), style_config, get_style(style_config, 1), 1, 85, "xiaomi")
    stripped = process._ProcessingState(str(source), "", str(source), style_config, get_style(style_config, 1), 1, 85, "xiaomi")
    try:
        process._detect_format(prepared, preserve_hdr=preserve_hdr)
        if prepared.motion_session is None:
            pytest.skip("Fixture does not contain Motion Photo data")
        process._detect_format(stripped, preserve_motion=False, preserve_hdr=preserve_hdr)
        process._load_image(prepared)
        process._load_image(stripped)
        assert stripped.motion_session is None
        assert stripped.image.size == prepared.image.size
        assert stripped.image.tobytes() == prepared.image.tobytes()
        assert stripped.image.info.get("exif") == prepared.image.info.get("exif")
        if prepared.ultrahdr_parts is not None:
            assert stripped.ultrahdr_parts.gainmap_jpeg == prepared.ultrahdr_parts.gainmap_jpeg
    finally:
        process._cleanup(prepared)
        process._cleanup(stripped)


def test_stripping_motion_preserves_hdr_after_large_jpeg_metadata(style_config, tmp_path, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "motion_photo.jpg"
    if not fixture.exists():
        pytest.skip("Real Motion Photo fixture is unavailable")
    original = fixture.read_bytes()
    baseline_gainmap = split_ultrahdr(original).gainmap_jpeg
    app2_payload = b"metadata padding".ljust(40000, b" ")
    app2_segment = b"\xff\xe2" + (len(app2_payload) + 2).to_bytes(2, "big") + app2_payload
    padded_path = tmp_path / "large-metadata-motion.jpg"
    padded_path.write_bytes(original[:2] + app2_segment * 2 + original[2:])
    kept = process._ProcessingState(str(padded_path), "", str(padded_path), style_config, get_style(style_config, 1), 1, 85, "xiaomi")
    stripped = process._ProcessingState(str(padded_path), "", str(padded_path), style_config, get_style(style_config, 1), 1, 85, "xiaomi")
    try:
        process._detect_format(kept, preserve_motion=True, preserve_hdr=True)
        process._detect_format(stripped, preserve_motion=False, preserve_hdr=True)
        assert kept.motion_session is not None
        assert kept.ultrahdr_parts is not None
        assert stripped.motion_session is None
        assert stripped.ultrahdr_parts is not None
        assert stripped.ultrahdr_parts.gainmap_jpeg == kept.ultrahdr_parts.gainmap_jpeg == baseline_gainmap
        assert process.detect_image_features(str(padded_path)) == {"is_hdr": True, "is_motion": True}
    finally:
        process._cleanup(kept)
        process._cleanup(stripped)

    def unchanged_canvas(image, *args, **kwargs):
        return image.copy(), {"content_box": (0, 0, *image.size), "final_size": image.size}

    monkeypatch.setattr(process, "generate_watermark_image", unchanged_canvas)
    result = process.process_image(str(padded_path), style_config=style_config, preserve_motion=False, preserve_hdr=True)
    assert result.is_hdr is True
    assert result.is_motion is False
    output = padded_path.with_name(padded_path.stem + "_watermark.jpg")
    assert split_ultrahdr(output.read_bytes()).gainmap_jpeg == baseline_gainmap
