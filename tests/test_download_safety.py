import io
import os
import tempfile
import zipfile

from services.download_token import build_signed_url, generate_token


def _item(filename):
    token, expires = generate_token(filename, action="download", burn="0")
    return {"filename": filename, "token": token, "expires": expires}


def _zip_setup(app, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    source = os.path.join(app.config["UPLOAD_FOLDER"], "result.jpg")
    with open(source, "wb") as stream:
        stream.write(b"image" * 200)
    return source


def test_zip_deduplicates_valid_items(app, client, tmp_path, monkeypatch):
    _zip_setup(app, tmp_path, monkeypatch)
    response = client.post("/api/download_zip", json={"items": [_item("result.jpg")] * 50})
    assert response.status_code == 200
    response = client.get(response.json["zip_url"])
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.namelist() == ["result.jpg"]
    response.close()


def test_zip_rejects_total_input_bytes(app, client, tmp_path, monkeypatch):
    _zip_setup(app, tmp_path, monkeypatch)
    app.config["ZIP_MAX_TOTAL_BYTES"] = 999
    response = client.post("/api/download_zip", json={"items": [_item("result.jpg")]})
    assert response.status_code == 413
    assert not list(tmp_path.glob("watermark_*.zip"))


def test_zip_rejects_temp_quota(app, client, tmp_path, monkeypatch):
    _zip_setup(app, tmp_path, monkeypatch)
    (tmp_path / "watermark_existing.zip").write_bytes(b"x" * 1000)
    app.config["ZIP_TEMP_QUOTA_BYTES"] = 1500
    response = client.post("/api/download_zip", json={"items": [_item("result.jpg")]})
    assert response.status_code == 503
    assert len(list(tmp_path.glob("watermark_*.zip"))) == 1


def test_zip_removes_partial_archive(app, client, tmp_path, monkeypatch):
    _zip_setup(app, tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(zipfile.ZipFile, "open", fail)
    response = client.post("/api/download_zip", json={"items": [_item("result.jpg")]})
    assert response.status_code == 500
    assert not list(tmp_path.glob("watermark_*.zip"))


def test_zip_rejects_overlapping_creation(app, client, tmp_path, monkeypatch):
    from routes.download import _zip_creation_lock
    _zip_setup(app, tmp_path, monkeypatch)
    with _zip_creation_lock:
        response = client.post("/api/download_zip", json={"items": [_item("result.jpg")]})
    assert response.status_code == 503


def test_burn_response_close_deletes_result_and_recorded_original(app, client):
    state = app.extensions["state"]
    folder = app.config["UPLOAD_FOLDER"]
    original = os.path.join(folder, "owned.jpg")
    output = os.path.join(folder, "owned_watermark.jpg")
    for filename in (original, output):
        with open(filename, "wb") as stream:
            stream.write(b"photo")
    state.create_task("burn-owner", {"status": "succeeded", "filepath": original, "burn_after_read": "1"})
    url = build_signed_url("/api/download/owned_watermark.jpg", "owned_watermark.jpg", action="download", burn="1")
    response = client.get(url, buffered=False)
    assert response.status_code == 200
    assert response.data == b"photo"
    response.close()
    assert not os.path.exists(original)
    assert not os.path.exists(output)
    assert not any(name.startswith(".burn_") for name in os.listdir(folder))


def test_burn_does_not_delete_unrelated_name_pair(app, client):
    folder = app.config["UPLOAD_FOLDER"]
    for name in ("unrelated.jpg", "unrelated_watermark.jpg"):
        with open(os.path.join(folder, name), "wb") as stream:
            stream.write(b"photo")
    url = build_signed_url("/api/download/unrelated_watermark.jpg", "unrelated_watermark.jpg", action="download", burn="1")
    response = client.get(url)
    assert response.status_code == 200
    response.close()
    assert os.path.exists(os.path.join(folder, "unrelated.jpg"))
    assert not any(name.startswith(".burn_") for name in os.listdir(folder))


def test_burn_disconnect_closes_and_removes_file(app, client):
    folder = app.config["UPLOAD_FOLDER"]
    with open(os.path.join(folder, "large.jpg"), "wb") as stream:
        stream.write(b"x" * 65536)
    url = build_signed_url("/api/download/large.jpg", "large.jpg", action="download", burn="1")
    response = client.get(url, buffered=False)
    assert response.status_code == 200
    response.close()  # Client disconnects before consuming the remaining bytes.
    assert not any(name.startswith(".burn_") for name in os.listdir(folder))


def test_zip_malformed_json_returns_client_error(client):
    for payload in ([], {"items": 2}, {"items": [None]}, {"items": [{"filename": 4}]}):
        assert client.post("/api/download_zip", json=payload).status_code == 400


def test_burn_failed_unlink_keeps_persisted_fallback(app, client, monkeypatch):
    import routes.download_file as download_module
    folder = app.config["UPLOAD_FOLDER"]
    with open(os.path.join(folder, "pending.jpg"), "wb") as stream:
        stream.write(b"photo")
    url = build_signed_url("/api/download/pending.jpg", "pending.jpg", action="download", burn="1")
    response = client.get(url, buffered=False)
    assert response.status_code == 200
    actual_remove = os.remove
    def fail_burn(path):
        if os.path.basename(path).startswith(".burn_"):
            raise PermissionError("busy")
        return actual_remove(path)
    monkeypatch.setattr(download_module.os, "remove", fail_burn)
    response.close()
    hidden = [os.path.join(folder, name) for name in os.listdir(folder) if name.startswith(".burn_")]
    assert len(hidden) == 1
    assert hidden[0] in app.extensions["state"].get_expired_burn_files(float("inf"))


def test_zip_rejects_non_string_or_non_ascii_token(client):
    for token in (12, "密钥"):
        item = _item("result.jpg")
        item["token"] = token
        assert client.post("/api/download_zip", json={"items": [item]}).status_code == 403
