import io
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from services.download_token import build_signed_url


@pytest.mark.parametrize("image_format", ["GIF", "TIFF", "BMP"])
def test_upload_rejects_disguised_image_before_metadata(client, monkeypatch, image_format):
    from services import upload_workflow
    metadata = Mock(side_effect=AssertionError("metadata parser reached"))
    monkeypatch.setattr(upload_workflow, "detect_manufacturer", metadata)
    data = io.BytesIO()
    Image.new("RGB", (2, 2)).save(data, format=image_format)
    data.seek(0)
    response = client.post("/api/upload", data={"file": (data, "disguised.jpg")})
    assert response.status_code == 400
    metadata.assert_not_called()
    assert not list(Path(client.application.config["UPLOAD_FOLDER"]).glob("photo_*"))


def test_upload_rejects_malformed_jpeg_before_metadata(client, monkeypatch):
    from services import upload_workflow
    metadata = Mock(side_effect=AssertionError("metadata parser reached"))
    monkeypatch.setattr(upload_workflow, "detect_manufacturer", metadata)
    response = client.post("/api/upload", data={"file": (io.BytesIO(b"\xff\xd8\xffbad"), "bad.jpg")})
    assert response.status_code == 400
    metadata.assert_not_called()


@pytest.mark.parametrize("path", ["/api/status/missing", "/api/upload/missing.jpg", "/api/download/missing.jpg"])
def test_api_responses_cannot_be_cached(client, path):
    response = client.get(path)
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("action,path", [("preview", "/api/upload/"), ("download", "/api/download/")])
def test_private_files_cannot_be_cached(app, client, action, path):
    (Path(app.config["UPLOAD_FOLDER"]) / "photo.jpg").write_bytes(b"photo")
    claims = {"action": action}
    if action == "download":
        claims["burn"] = "0"
    response = client.get(build_signed_url(path + "photo.jpg", "photo.jpg", **claims))
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    response.close()


@pytest.mark.parametrize("headers", [
    {"Origin": "https://attacker.example"},
    {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_cross_site_upload_rejected_before_parsing(client, headers):
    response = client.post("/api/upload", headers=headers)
    assert response.status_code == 403


def test_same_origin_and_cli_uploads_reach_validation(client):
    assert client.post("/api/upload", headers={"Origin": "http://localhost"}).status_code == 400
    assert client.post("/api/upload").status_code == 400


@pytest.mark.parametrize("endpoint", ["confirm_logo", "confirm_options"])
@pytest.mark.parametrize("payload", [[1], {"task_id": ["invalid"]}, {"task_id": {"invalid": True}}])
def test_invalid_confirmation_json_is_a_client_error(client, endpoint, payload):
    response = client.post(f"/api/upload/{endpoint}", json=payload)
    assert response.status_code == 400


def test_invalid_token_unicode_never_causes_server_error(client):
    response = client.get("/api/upload/photo.jpg", query_string={"token": "密钥", "expires": "9999999999"})
    assert response.status_code == 403


def test_json_api_body_has_small_limit(client):
    response = client.post("/api/upload/confirm_logo", json={"task_id": "x" * 20000})
    assert response.status_code == 413


def test_security_headers_prohibit_embedded_objects(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    for directive in ("object-src 'none'", "base-uri 'self'", "frame-ancestors 'none'"):
        assert directive in csp


def test_untrusted_forwarded_headers_are_ignored(client):
    response = client.post("/api/upload", headers={
        "Origin": "https://attacker.example", "X-Forwarded-Host": "attacker.example",
        "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.1",
    })
    assert response.status_code == 403


@pytest.mark.parametrize("secret", ["short", "replace-with-a-strong-secret", "__CHANGE_ME__"])
def test_startup_rejects_weak_signing_secret(tmp_path, monkeypatch, secret):
    from app_factory import create_app
    monkeypatch.setenv("DOWNLOAD_TOKEN_SECRET", secret)
    with pytest.raises(RuntimeError, match="DOWNLOAD_TOKEN_SECRET"):
        create_app({"UPLOAD_FOLDER": str(tmp_path), "START_BACKGROUND_CLEANER": False})


@pytest.mark.parametrize("image_format", ["JPEG", "PNG"])
def test_valid_uploads_still_reach_processing(client, monkeypatch, image_format):
    from services import upload_workflow
    monkeypatch.setattr(upload_workflow, "detect_manufacturer", lambda *args: "Canon")
    submit = Mock(return_value="valid-task")
    monkeypatch.setattr(upload_workflow, "submit_task", submit)
    data = io.BytesIO()
    Image.new("RGB", (2, 2)).save(data, format=image_format)
    data.seek(0)
    response = client.post("/api/upload", data={"file": (data, "image." + image_format.lower())})
    assert response.status_code == 202
    submit.assert_called_once()


@pytest.mark.parametrize("status", ["queued", "processing", "needs_logo", "needs_options"])
def test_all_outstanding_tasks_count_before_metadata(app, client, monkeypatch, status):
    from constants import AppConstants
    from services import upload_workflow
    for index in range(AppConstants.MAX_PENDING_TASKS):
        app.extensions["state"].create_task(str(index), {"status": status})
    metadata = Mock(side_effect=AssertionError("metadata parser reached"))
    monkeypatch.setattr(upload_workflow, "detect_manufacturer", metadata)
    response = client.post("/api/upload", data={"file": (io.BytesIO(b"data"), "image.jpg")})
    assert response.status_code == 503
    metadata.assert_not_called()
    assert not list(Path(app.config["UPLOAD_FOLDER"]).glob("photo_*"))


def test_overlapping_upload_preprocessing_is_rejected(app, client):
    with app.extensions["state"].upload_lock:
        response = client.post("/api/upload", data={"file": (io.BytesIO(b"data"), "image.jpg")})
    assert response.status_code == 503


def test_multipart_part_count_is_bounded(client):
    response = client.post("/api/upload", data={str(i): "x" for i in range(17)}, content_type="multipart/form-data")
    assert response.status_code == 413


def test_multipart_file_larger_than_parser_buffer_is_accepted(client, monkeypatch):
    from services import upload_workflow
    monkeypatch.setattr(upload_workflow, "detect_manufacturer", lambda *args: "Canon")
    monkeypatch.setattr(upload_workflow, "submit_task", lambda *args: "valid-task")
    data = io.BytesIO()
    with Image.frombytes("RGB", (256, 256), os.urandom(256 * 256 * 3)) as image:
        image.save(data, format="PNG")
    assert data.tell() > 128 * 1024
    data.seek(0)
    response = client.post("/api/upload", data={"file": (data, "image.png")})
    assert response.status_code == 202


def test_signed_state_database_is_not_an_image_download(app, client):
    filename = Path(app.config["STATE_DB_PATH"]).name
    for action, prefix in [("preview", "/api/upload/"), ("download", "/api/download/")]:
        claims = {"action": action}
        if action == "download":
            claims["burn"] = "0"
        response = client.get(build_signed_url(prefix + filename, filename, **claims))
        assert response.status_code in {400, 403, 404}


def test_host_allowlist_is_enforced(app, client):
    app.config["TRUSTED_HOSTS"] = ["photos.example"]
    assert client.get("/", base_url="http://photos.example").status_code == 200
    assert client.get("/", base_url="http://attacker.example").status_code == 400


def test_trusted_proxy_only_honors_headers_from_configured_peer():
    from services.trusted_proxy import TrustedProxyFix
    from werkzeug.test import Client
    from werkzeug.wrappers import Request, Response

    @Request.application
    def inspect(request):
        return Response(f"{request.remote_addr}|{request.scheme}|{request.host}")

    client = Client(TrustedProxyFix(inspect, ["192.0.2.10/32"]), Response)
    headers = {"X-Forwarded-For": "203.0.113.10, 198.51.100.20", "X-Forwarded-Proto": "https",
               "X-Forwarded-Host": "attacker.example"}
    response = client.get("/", headers=headers, environ_overrides={"REMOTE_ADDR": "192.0.2.10"})
    assert response.text == "198.51.100.20|https|localhost"
    response = client.get("/", headers=headers, environ_overrides={"REMOTE_ADDR": "192.0.2.11"})
    assert response.text == "192.0.2.11|http|localhost"


def test_https_security_headers(client):
    assert client.get("/", base_url="https://localhost").headers["Strict-Transport-Security"] == "max-age=31536000"
    assert "Strict-Transport-Security" not in client.get("/").headers
