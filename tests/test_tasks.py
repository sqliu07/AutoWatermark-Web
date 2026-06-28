import logging
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from PIL import Image

from errors import WatermarkError, WatermarkErrorCode
from process import _save_output
from process_result import ProcessResult
from services.state import AppState
from services.tasks import TaskPayload, background_process, submit_existing_task


def test_background_process_logs_unexpected_watermark_detail(monkeypatch, caplog, tmp_path):
    task_id = "task-unexpected"
    state = AppState(str(tmp_path / "state.sqlite3"))
    state.create_task(task_id, {"status": "queued", "submitted_at": 0, "progress": 0.0, "stage": "queued"})

    def fake_process_image(*args, **kwargs):
        raise WatermarkError(WatermarkErrorCode.UNEXPECTED_ERROR, detail="render caption failed")

    monkeypatch.setattr("services.tasks.process_image", fake_process_image)

    logger = logging.getLogger("tests.background_process")

    payload = TaskPayload(
        task_id=task_id,
        state=state,
        filepath=str(tmp_path / "sample.jpg"),
        lang="zh",
        watermark_type=5,
        image_quality=85,
        burn_after_read="0",
        logo_preference=None,
        style_config={},
        logger=logger,
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        background_process(payload)

    task = state.get_task(task_id)
    assert task["status"] == "failed"
    # unexpected_error 不向客户端暴露内部详情，返回通用错误消息
    assert "render caption failed" not in task["error"]
    assert task["error"] == "处理水印时发生未知错误。"
    # 但日志中仍然记录了详细信息
    assert "render caption failed" in caplog.text
    assert "style=5" in caplog.text


def test_background_process_returns_signed_preview_download_and_motion_urls(monkeypatch, tmp_path):
    task_id = "task-success"
    state = AppState(str(tmp_path / "state.sqlite3"))
    state.create_task(task_id, {"status": "queued", "submitted_at": 0, "progress": 0.0, "stage": "queued"})

    def fake_process_image(*_args, **_kwargs):
        return ProcessResult(is_motion=True)

    monkeypatch.setattr("services.tasks.process_image", fake_process_image)

    payload = TaskPayload(
        task_id=task_id,
        state=state,
        filepath=str(tmp_path / "sample.jpg"),
        lang="en",
        watermark_type=1,
        image_quality=85,
        burn_after_read="1",
        logo_preference=None,
        style_config={},
        logger=logging.getLogger("tests.background_process"),
    )

    background_process(payload)

    task = state.get_task(task_id)
    assert task["status"] == "succeeded"
    result = task["result"]

    preview_query = parse_qs(urlparse(result["preview_url"]).query)
    download_query = parse_qs(urlparse(result["download_url"]).query)
    motion_query = parse_qs(urlparse(result["motion_video_url"]).query)

    assert preview_query["action"] == ["preview"]
    assert download_query["action"] == ["download"]
    assert download_query["burn"] == ["1"]
    assert motion_query["action"] == ["motion_video"]
    assert result["is_motion"] is True


def test_background_process_passes_media_preserve_choices(monkeypatch, tmp_path):
    task_id = "task-preserve-options"
    state = AppState(str(tmp_path / "state.sqlite3"))
    state.create_task(task_id, {"status": "queued", "submitted_at": 0, "progress": 0.0, "stage": "queued"})

    seen_kwargs = {}

    def fake_process_image(*_args, **kwargs):
        seen_kwargs.update(kwargs)
        return ProcessResult(is_hdr=True)

    monkeypatch.setattr("services.tasks.process_image", fake_process_image)

    payload = TaskPayload(
        task_id=task_id,
        state=state,
        filepath=str(tmp_path / "sample.jpg"),
        lang="en",
        watermark_type=1,
        image_quality=85,
        burn_after_read="0",
        logo_preference=None,
        style_config={},
        logger=logging.getLogger("tests.background_process"),
        preserve_motion=False,
        preserve_hdr=True,
    )

    background_process(payload)

    assert seen_kwargs["preserve_motion"] is False
    assert seen_kwargs["preserve_hdr"] is True
    assert state.get_task(task_id)["result"]["is_hdr"] is True


def test_submit_existing_task_persists_media_preserve_fields(monkeypatch, tmp_path):
    task_id = "persist-options"
    state = AppState(str(tmp_path / "state.sqlite3"))
    state.create_task(
        task_id,
        {
            "status": "needs_options",
            "submitted_at": 0,
            "progress": 0.0,
            "stage": "awaiting_options",
            "features": {"is_hdr": True, "is_motion": True},
        },
    )

    submitted = {}

    class FakeExecutor:
        def submit(self, fn, payload):
            submitted["fn"] = fn
            submitted["payload"] = payload

    state.executor = FakeExecutor()

    payload = TaskPayload(
        task_id=task_id,
        state=state,
        filepath=str(tmp_path / "sample.jpg"),
        lang="en",
        watermark_type=1,
        image_quality=85,
        burn_after_read="0",
        logo_preference="xiaomi",
        style_config={},
        logger=logging.getLogger("tests.background_process"),
        preliminary_manufacturer="Canon",
        preserve_motion=False,
        preserve_hdr=True,
    )

    submit_existing_task(task_id, payload)

    task = state.get_task(task_id)
    assert task["status"] == "queued"
    assert task["preliminary_manufacturer"] == "Canon"
    assert task["preserve_motion"] is False
    assert task["preserve_hdr"] is True
    assert submitted["payload"].preserve_motion is False


def test_save_output_reports_hdr_only_when_preserved(tmp_path):
    output_path = tmp_path / "output.jpg"
    state = SimpleNamespace(
        motion_session=None,
        watermark_metadata=None,
        ultrahdr_parts=object(),
        style={"supports_ultrahdr": True},
        watermark_type=1,
        new_image=Image.new("RGB", (2, 2), "white"),
        output_path=str(output_path),
        exif_bytes=b"",
        image_quality=85,
    )

    result = _save_output(
        state,
        preview=False,
        advance_progress=lambda _stage: None,
        preserve_motion=True,
        preserve_hdr=False,
    )

    assert result.is_hdr is False
    assert output_path.exists()


def test_save_output_can_strip_hdr_from_motion_photo(tmp_path):
    output_path = tmp_path / "motion.jpg"

    class FakeMotionSession:
        ultrahdr_gainmap_jpeg = b"gainmap"
        ultrahdr_gainmap_xmp = b"xmp"
        ultrahdr_primary_size = (2, 2)
        still_path = tmp_path / "still.jpg"

        def finalize(self, _watermarked_path, final_path, _metadata):
            final_path.write_bytes(b"motion")

    state = SimpleNamespace(
        motion_session=FakeMotionSession(),
        watermark_metadata={"overlay_image": object(), "content_box": (0, 0, 2, 2)},
        ultrahdr_parts=object(),
        style={"supports_motion": True, "supports_ultrahdr": True},
        watermark_type=1,
        new_image=Image.new("RGB", (2, 2), "white"),
        output_path=str(output_path),
        exif_bytes=b"",
        image_quality=85,
    )

    result = _save_output(
        state,
        preview=False,
        advance_progress=lambda _stage: None,
        preserve_motion=True,
        preserve_hdr=False,
    )

    assert result.is_motion is True
    assert result.is_hdr is False
    assert state.motion_session.ultrahdr_gainmap_jpeg is None
    assert output_path.read_bytes() == b"motion"
