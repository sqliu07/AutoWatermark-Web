import io
import zipfile
from pathlib import Path
from urllib.parse import unquote

import pytest
from PIL import Image

from services.download_token import build_signed_url, generate_token
from services.state import AppState


def _saved_task(app, filename, original_name):
    folder = Path(app.config["UPLOAD_FOLDER"])
    source = folder / filename
    result = folder / (source.stem + "_watermark" + source.suffix)
    result.write_bytes(b"full photo")
    app.extensions["state"].create_task(filename, {
        "status": "succeeded", "filepath": str(source), "original_name": original_name,
    })
    return result


def test_attachment_uses_original_unicode_name_without_changing_storage(app, client):
    result = _saved_task(app, "photo_random.jpg", "旅拍.jpeg")
    url = build_signed_url("/api/download/" + result.name, result.name, action="download", burn="0")
    response = client.get(url)
    assert response.status_code == 200
    assert "旅拍_watermark.jpg" in unquote(response.headers["Content-Disposition"])
    assert response.data == b"full photo"
    assert result.exists()
    response.close()


def test_zip_uses_original_names_and_keeps_duplicate_photos(app, client):
    results = [_saved_task(app, f"photo_{i}.jpg", "照片.jpg") for i in range(2)]
    items = []
    for path in results:
        token, expires = generate_token(path.name, action="download", burn="0")
        items.append({"filename": path.name, "token": token, "expires": expires})
    response = client.post("/api/download_zip", json={"items": items})
    assert response.status_code == 200
    download = client.get(response.json["zip_url"])
    assert "AutoWatermark.zip" in download.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        assert set(archive.namelist()) == {"照片_watermark.jpg", "照片_watermark (2).jpg"}
        assert all(archive.read(name) == b"full photo" for name in archive.namelist())
    download.close()


def test_download_name_removes_path_and_header_control_characters(app):
    result = _saved_task(app, "photo_random.jpg", "../folder\\照片\r\n.jpeg")
    assert app.extensions["state"].get_download_name(str(result)) == "照片_watermark.jpg"


def test_original_name_survives_restart(tmp_path):
    database = str(tmp_path / "state.db")
    state = AppState(database)
    source = tmp_path / "photo_random.png"
    state.create_task("persist", {"status": "succeeded", "filepath": str(source), "original_name": "source.png"})
    state.shutdown()
    state = AppState(database)
    try:
        assert state.get_task("persist")["original_name"] == "source.png"
        assert state.get_download_name(str(tmp_path / "photo_random_watermark.png")) == "source_watermark.png"
    finally:
        state.shutdown()


@pytest.mark.parametrize("filename,image_format", [("我的照片.jpg", "JPEG"), ("我的照片.png", "PNG")])
def test_upload_remembers_original_name_before_logo_confirmation(app, client, monkeypatch, filename, image_format):
    monkeypatch.setattr("services.upload_workflow.detect_manufacturer", lambda *args: "Xiaomi")
    data = io.BytesIO()
    with Image.new("RGB", (2, 2)) as image:
        image.save(data, image_format)
    data.seek(0)
    response = client.post("/api/upload", data={"file": (data, filename)})
    assert response.status_code == 200
    task = app.extensions["state"].get_task(response.json["task_id"])
    assert task["original_name"] == filename
    assert Path(task["filepath"]).name != filename
    assert Path(task["filepath"]).suffix == Path(filename).suffix
