import io
import os
import pathlib
import shutil

import pytest
from PIL import Image

import routes.upload as upload_routes
from constants import ImageConstants
from errors import ImageTooLargeError, MissingExifDataError, UnsupportedManufacturerError
from exif import find_logo, get_manufacturer
from media.motion_photo import prepare_motion_photo
from process import process_image
from media.ultrahdr import split_ultrahdr
from services.download_token import generate_token

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "tests" / "fixtures"

SAMPLE_IMAGE = ASSETS_DIR / "sample_with_exif.jpg"
MOTION_IMAGE = ASSETS_DIR / "motion_photo.jpg"
ULTRAHDR_IMAGE = ASSETS_DIR / "ultrahdr.jpg"
NO_EXIF_IMAGE = ASSETS_DIR / "no_exif.jpg"
UNSUPPORTED_IMAGE = ASSETS_DIR / "unsupported_brand.jpg"


def require_asset(path: pathlib.Path, hint: str) -> None:
    if not path.exists():
        pytest.skip(f"Missing test asset: {path.name}. {hint}")


def test_index_ok(client):
    response = client.get("/")
    assert response.status_code == 200


def test_unknown_path_browser_redirects_home(client):
    response = client.get("/123", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_unknown_path_api_keeps_json_404(client):
    response = client.get("/123", headers={"Accept": "application/json"})
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["error"]


def test_upload_missing_file(client):
    response = client.post("/upload")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "未上传文件！"


def test_upload_get_redirects_home(client):
    response = client.get("/upload")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_confirm_logo_get_redirects_home(client):
    response = client.get("/upload/confirm_logo")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_upload_invalid_extension(client):
    data = {"file": (io.BytesIO(b"hello"), "sample.txt")}
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "无效的文件类型！请上传PNG、JPG或JPEG文件。"


def test_status_unknown(client):
    response = client.get("/status/does-not-exist")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["status"] == "unknown"


def test_download_zip_no_files(client):
    response = client.post("/download_zip", json={})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]  # 错误消息已 i18n，只验证非空


def test_download_zip_get_redirects_home(client):
    response = client.get("/download_zip")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_upload_invalid_watermark_type(client):
    data = {
        "file": (io.BytesIO(b"not-an-image"), "sample.jpg"),
        "watermark_type": "abc",
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "处理水印时发生未知错误。"


def test_upload_unknown_watermark_type(client):
    data = {
        "file": (io.BytesIO(b"not-an-image"), "sample.jpg"),
        "watermark_type": "9999",
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "处理水印时发生未知错误。"


def test_upload_xiaomi_requires_logo_choice(client, monkeypatch):
    monkeypatch.setattr(upload_routes, "detect_manufacturer", lambda _: "xiaomi")
    data = {
        "file": (io.BytesIO(b"fake"), "sample.jpg"),
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["needs_logo_choice"] is True
    assert payload["task_id"]


def test_upload_success_returns_task_id(client, monkeypatch):
    def fake_submit_task(*args, **kwargs):
        return "task-123"

    monkeypatch.setattr(upload_routes, "submit_task", fake_submit_task)

    data = {
        "file": (io.BytesIO(b"fake"), "sample.jpg"),
        "watermark_type": "1",
    }
    response = client.post("/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 202
    payload = response.get_json()
    assert payload["task_id"] == "task-123"


def test_confirm_logo_choice_submits_existing_task(client, monkeypatch):
    monkeypatch.setattr(upload_routes, "detect_manufacturer", lambda _: "xiaomi")

    submitted = {}

    def fake_submit_existing_task(task_id, *_args, **_kwargs):
        submitted["task_id"] = task_id
        return task_id

    monkeypatch.setattr(upload_routes, "submit_existing_task", fake_submit_existing_task)

    upload_response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake"), "sample.jpg")},
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    task_id = upload_response.get_json()["task_id"]

    confirm_response = client.post(
        "/upload/confirm_logo",
        json={"task_id": task_id, "logo_preference": "leica"},
    )
    assert confirm_response.status_code == 202
    payload = confirm_response.get_json()
    assert payload["task_id"] == task_id
    assert submitted["task_id"] == task_id


def test_upload_burn_after_read_updates_queue(client):
    app = client.application
    upload_dir = app.config["UPLOAD_FOLDER"]
    filename = "burn.jpg"
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"burn")

    token, expires = generate_token(filename)
    response = client.get(f"/upload/{filename}?burn=1&token={token}&expires={expires}")
    assert response.status_code == 200

    state = app.extensions["state"]
    assert file_path in state.burn_queue


def test_download_zip_with_valid_file(client):
    app = client.application
    upload_dir = app.config["UPLOAD_FOLDER"]
    filename = "zip.jpg"
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"zip")

    response = client.post("/download_zip", json={"filenames": [filename]})
    assert response.status_code == 200
    payload = response.get_json()
    zip_url = payload["zip_url"]
    zip_name = zip_url.split("/")[-1]

    download_response = client.get(f"/download_temp_zip/{zip_name}")
    assert download_response.status_code == 200


def test_download_temp_zip_browser_invalid_token_redirects_home(client):
    response = client.get("/download_temp_zip/demo.zip", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_upload_motion_video_streams_mp4(client):
    app = client.application
    upload_dir = app.config["UPLOAD_FOLDER"]
    filename = "motion.jpg"
    file_path = os.path.join(upload_dir, filename)

    fake_mp4 = (
        b"\x00\x00\x00\x18ftypisom"
        b"\x00\x00\x02\x00isomiso2"
    )
    xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:Description GCamera:MotionPhotoOffset="%d" />'
        b"</x:xmpmeta>" % len(fake_mp4)
    )
    fake_jpeg = b"\xff\xd8" + xmp + b"\xff\xd9"
    with open(file_path, "wb") as f:
        f.write(fake_jpeg + fake_mp4)

    token, expires = generate_token(filename)
    response = client.get(f"/upload/{filename}/video?token={token}&expires={expires}")
    assert response.status_code == 200
    assert response.mimetype == "video/mp4"
    assert response.data == fake_mp4


def test_process_image_with_real_photo(tmp_path):
    require_asset(SAMPLE_IMAGE, "Place a real JPEG with EXIF under tests/fixtures.")

    temp_image = tmp_path / SAMPLE_IMAGE.name
    temp_image.write_bytes(SAMPLE_IMAGE.read_bytes())

    manufacturer = get_manufacturer(str(temp_image))
    if not manufacturer or not find_logo(manufacturer):
        pytest.skip("Sample photo manufacturer not supported by logos")

    result = process_image(
        str(temp_image),
        watermark_type=1,
        image_quality=85,
        logo_preference="xiaomi",
    )
    assert result is True

    output_path = temp_image.with_name(f"{temp_image.stem}_watermark{temp_image.suffix}")
    assert output_path.exists()


def test_process_image_missing_exif(tmp_path):
    require_asset(NO_EXIF_IMAGE, "Provide a JPEG without EXIF (e.g., screenshot export).")

    temp_image = tmp_path / NO_EXIF_IMAGE.name
    temp_image.write_bytes(NO_EXIF_IMAGE.read_bytes())

    with pytest.raises(MissingExifDataError):
        process_image(
            str(temp_image),
            watermark_type=1,
            image_quality=85,
            logo_preference="xiaomi",
        )


def test_process_image_unsupported_manufacturer(tmp_path):
    require_asset(UNSUPPORTED_IMAGE, "Provide a JPEG with EXIF from an unsupported brand.")

    temp_image = tmp_path / UNSUPPORTED_IMAGE.name
    temp_image.write_bytes(UNSUPPORTED_IMAGE.read_bytes())

    manufacturer = get_manufacturer(str(temp_image))
    if not manufacturer:
        pytest.skip("Unsupported-brand asset is missing EXIF manufacturer")
    if find_logo(manufacturer):
        pytest.skip("Asset brand is supported; choose a photo without a matching logo")

    with pytest.raises(UnsupportedManufacturerError):
        process_image(
            str(temp_image),
            watermark_type=1,
            image_quality=85,
            logo_preference="xiaomi",
        )


def test_process_motion_photo_with_real_photo(tmp_path):
    require_asset(MOTION_IMAGE, "Provide a motion photo JPEG with embedded video.")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available for motion photo watermarking")

    temp_image = tmp_path / MOTION_IMAGE.name
    temp_image.write_bytes(MOTION_IMAGE.read_bytes())

    session = prepare_motion_photo(str(temp_image))
    if not session or not session.has_motion:
        if session:
            session.cleanup()
        pytest.skip("Motion metadata not found in motion asset")
    session.cleanup()

    manufacturer = get_manufacturer(str(temp_image))
    if not manufacturer or not find_logo(manufacturer):
        pytest.skip("Motion asset manufacturer not supported by logos")

    result = process_image(
        str(temp_image),
        watermark_type=1,
        image_quality=85,
        logo_preference="xiaomi",
    )
    assert result is True

    output_path = temp_image.with_name(f"{temp_image.stem}_watermark{temp_image.suffix}")
    assert output_path.exists()


def test_process_ultrahdr_photo_with_real_asset(tmp_path):
    require_asset(ULTRAHDR_IMAGE, "Provide an Ultra HDR JPEG_R sample.")

    data = ULTRAHDR_IMAGE.read_bytes()
    try:
        parts = split_ultrahdr(data)
    except Exception:
        pytest.skip("Asset is not a valid Ultra HDR container")
    if not parts or not parts.gainmap_jpeg:
        pytest.skip("Asset does not contain a gain map")

    temp_image = tmp_path / ULTRAHDR_IMAGE.name
    temp_image.write_bytes(data)

    manufacturer = get_manufacturer(str(temp_image))
    if not manufacturer or not find_logo(manufacturer):
        pytest.skip("Ultra HDR asset manufacturer not supported by logos")

    result = process_image(
        str(temp_image),
        watermark_type=1,
        image_quality=85,
        logo_preference="xiaomi",
    )
    assert result is True

    output_path = temp_image.with_name(f"{temp_image.stem}_watermark{temp_image.suffix}")
    assert output_path.exists()


def test_process_image_too_large(monkeypatch, tmp_path):
    monkeypatch.setattr(ImageConstants, "MAX_IMAGE_PIXELS", 1)
    temp_image = tmp_path / "tiny.jpg"
    Image.new("RGB", (2, 2), color=(255, 255, 255)).save(temp_image, format="JPEG")

    with pytest.raises(ImageTooLargeError):
        process_image(
            str(temp_image),
            watermark_type=1,
            image_quality=85,
            logo_preference="xiaomi",
        )
