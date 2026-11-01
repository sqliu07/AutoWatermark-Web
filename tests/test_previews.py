import io
import logging
import os
import time
from pathlib import Path

import pytest
from PIL import Image

from services.download_token import build_signed_url
from services.tasks import TaskPayload, background_process
from process_result import ProcessResult


def _make_result(path, size=(1800, 1200), image_format="JPEG"):
    with Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)) as image:
        image.save(path, format=image_format, quality=95)


def test_preview_generation_keeps_full_artifact_and_bounds_sizes(tmp_path):
    from services.previews import create_previews
    result = tmp_path / "photo_watermark.jpg"
    _make_result(result)
    original = result.read_bytes()
    previews = create_previews(str(result))
    assert result.read_bytes() == original
    assert set(previews) == {"preview", "thumbnail"}
    for kind, edge in (("preview", 1280), ("thumbnail", 160)):
        with Image.open(previews[kind]) as image:
            assert image.format == "JPEG"
            assert max(image.size) <= edge
            assert image.width / image.height == pytest.approx(1.5, abs=.01)
            assert not image.getexif()
        assert Path(previews[kind]).stat().st_size < len(original)


def test_transparent_png_preview_composites_on_white(tmp_path):
    from services.previews import create_previews
    result = tmp_path / "photo_watermark.png"
    with Image.new("RGBA", (20, 20), (0, 0, 0, 0)) as image:
        image.save(result)
    previews = create_previews(str(result))
    with Image.open(previews["preview"]) as image:
        assert image.getpixel((10, 10)) == (255, 255, 255)


@pytest.mark.parametrize("name", ["motion_photo.jpg", "ultrahdr.jpg"])
def test_previews_do_not_rewrite_embedded_media(tmp_path, name):
    from services.previews import create_previews
    source = Path(__file__).parent / "fixtures" / name
    if not source.exists():
        pytest.skip("real media fixture unavailable")
    result = tmp_path / name
    data = source.read_bytes()
    result.write_bytes(data)
    variants = create_previews(str(result))
    assert result.read_bytes() == data
    for path in variants.values():
        with Image.open(path) as image:
            assert image.format == "JPEG"
            assert getattr(image, "n_frames", 1) == 1


def test_preview_orientation_matches_full_image_display(tmp_path):
    from services.previews import create_previews
    result = tmp_path / "oriented.jpg"
    with Image.new("RGB", (80, 40), "blue") as image:
        exif = Image.Exif()
        exif[274] = 6
        image.save(result, exif=exif)
    previews = create_previews(str(result))
    with Image.open(previews["preview"]) as image:
        assert image.size == (40, 80)
        assert not image.getexif()


def test_preview_failure_removes_partial_derivatives(tmp_path, monkeypatch):
    from services import previews
    result = tmp_path / "photo_watermark.jpg"
    _make_result(result, (32, 32))
    original_save = Image.Image.save
    saves = []

    def fail_second(self, *args, **kwargs):
        saves.append(1)
        if len(saves) == 2:
            raise OSError("disk full")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_second)
    with pytest.raises(OSError):
        previews.create_previews(str(result))
    assert list(tmp_path.iterdir()) == [result]


def test_preview_storage_quota_keeps_only_full_result(tmp_path):
    from services.previews import create_previews
    result = tmp_path / "photo_watermark.jpg"
    _make_result(result, (32, 32))
    with pytest.raises(OSError):
        create_previews(str(result), storage_quota_bytes=result.stat().st_size)
    assert list(tmp_path.iterdir()) == [result]


def test_completed_task_returns_independently_signed_preview_variants(app, client, monkeypatch):
    folder = Path(app.config["UPLOAD_FOLDER"])
    original = folder / "source.jpg"
    output = folder / "source_watermark.jpg"
    _make_result(original, (32, 32))
    _make_result(output)
    full_bytes = output.read_bytes()
    state = app.extensions["state"]
    state.create_task("with-previews", {"status": "queued", "filepath": str(original)})
    progress_values = []
    update_task = state.update_task

    def record_update(*args, **kwargs):
        if "progress" in kwargs:
            progress_values.append(kwargs["progress"])
        return update_task(*args, **kwargs)

    def process(*args, **kwargs):
        kwargs["progress_callback"](1.0, "saved")
        return ProcessResult(is_hdr=True, is_motion=True)

    monkeypatch.setattr(state, "update_task", record_update)
    monkeypatch.setattr("services.tasks.process_image", process)
    payload = TaskPayload("with-previews", state, str(original), "en", 1, 95, "0", None, {}, app.logger)
    background_process(payload)
    assert progress_values == sorted(progress_values)
    assert progress_values[-1] == 1.0
    result = state.get_task("with-previews")["result"]
    assert result["is_hdr"] is True and result["is_motion"] is True
    assert len({result["preview_url"], result["thumbnail_url"], result["full_preview_url"]}) == 3
    for key, edge in (("preview_url", 1280), ("thumbnail_url", 160)):
        response = client.get(result[key])
        assert response.status_code == 200
        assert "no-store" in response.headers["Cache-Control"]
        with Image.open(io.BytesIO(response.data)) as image:
            assert max(image.size) <= edge
        response.close()
    response = client.get(result["full_preview_url"])
    assert response.data == full_bytes
    response.close()
    response = client.get(result["download_url"])
    assert response.data == full_bytes
    response.close()
    # Changing the signed target cannot promote a thumbnail token to a full photo.
    tampered = result["thumbnail_url"].replace(output.name + ".thumb.jpg", output.name)
    assert client.get(tampered).status_code == 403


def test_preview_failure_does_not_fail_finished_task(app, monkeypatch):
    folder = Path(app.config["UPLOAD_FOLDER"])
    source = folder / "photo.jpg"
    output = folder / "photo_watermark.jpg"
    _make_result(source, (16, 16))
    _make_result(output, (16, 16))
    state = app.extensions["state"]
    state.create_task("fallback", {"status": "queued", "filepath": str(source)})
    monkeypatch.setattr("services.tasks.process_image", lambda *args, **kwargs: ProcessResult())
    monkeypatch.setattr("services.tasks.create_previews", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("full")))
    background_process(TaskPayload("fallback", state, str(source), "en", 1, 95, "0", None, {}, app.logger))
    task = state.get_task("fallback")
    assert task["status"] == "succeeded"
    assert task["result"]["preview_url"] == task["result"]["full_preview_url"]
    assert task["result"]["thumbnail_url"] == task["result"]["full_preview_url"]


def test_burn_deletes_preview_derivatives_and_disables_old_links(app, client):
    from services.previews import create_previews
    folder = Path(app.config["UPLOAD_FOLDER"])
    source = folder / "photo.jpg"
    result = folder / "photo_watermark.jpg"
    _make_result(source, (32, 32))
    _make_result(result, (32, 32))
    previews = create_previews(str(result))
    state = app.extensions["state"]
    state.create_task("burn-previews", {"status": "succeeded", "filepath": str(source), "burn_after_read": "1"})
    preview_link = build_signed_url("/api/upload/" + Path(previews["preview"]).name, Path(previews["preview"]).name, action="preview")
    download_link = build_signed_url("/api/download/" + result.name, result.name, action="download", burn="1")
    assert client.get(preview_link).status_code == 200
    response = client.get(download_link, buffered=False)
    assert response.status_code == 200
    assert client.get(preview_link).status_code == 404
    response.close()
    assert not result.exists() and not source.exists()
    assert not any(Path(path).exists() for path in previews.values())


def test_stale_result_cleanup_removes_even_fresh_derivatives(tmp_path):
    from services.cleanup import _cleanup_stale_uploads
    from services.previews import create_previews
    from types import SimpleNamespace
    result = tmp_path / "photo_watermark.jpg"
    _make_result(result, (32, 32))
    previews = create_previews(str(result))
    old = time.time() - 2 * 86400
    os.utime(result, (old, old))
    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(tmp_path), "STATE_DB_PATH": None})
    _cleanup_stale_uploads(app, time.time(), logging.getLogger("test-previews"))
    assert not result.exists()
    assert not any(Path(path).exists() for path in previews.values())


def test_preview_cleanup_cannot_follow_a_link_to_state_database(tmp_path):
    from services.cleanup import _cleanup_stale_uploads
    from services.previews import preview_paths
    from types import SimpleNamespace
    result = tmp_path / "photo_watermark.jpg"
    _make_result(result, (32, 32))
    database = tmp_path / "app_state.sqlite3"
    database.write_bytes(b"private state")
    Path(preview_paths(str(result))["preview"]).symlink_to(database)
    old = time.time() - 2 * 86400
    os.utime(result, (old, old))
    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(tmp_path), "STATE_DB_PATH": str(database)})
    _cleanup_stale_uploads(app, time.time(), logging.getLogger("test-previews"))
    assert database.read_bytes() == b"private state"


def test_burn_never_schedules_or_deletes_linked_state_database(app, client):
    from services.previews import preview_paths
    result = Path(app.config["UPLOAD_FOLDER"]) / "photo_watermark.jpg"
    _make_result(result, (32, 32))
    database = Path(app.config["STATE_DB_PATH"])
    derivative = Path(preview_paths(str(result))["preview"])
    derivative.symlink_to(database)
    preview_link = build_signed_url("/api/upload/" + derivative.name, derivative.name, action="preview")
    assert client.get(preview_link).status_code == 404
    link = build_signed_url("/api/download/" + result.name, result.name, action="download", burn="1")
    response = client.get(link)
    assert response.status_code == 200
    response.close()
    assert database.is_file()
    assert str(database) not in app.extensions["state"].get_expired_burn_files(float("inf"))
