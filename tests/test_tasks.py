import logging
from urllib.parse import parse_qs, urlparse

from errors import WatermarkError, WatermarkErrorCode
from process_result import ProcessResult
from services.state import AppState
from services.tasks import TaskPayload, background_process


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
