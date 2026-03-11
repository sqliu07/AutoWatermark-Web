import logging

from errors import UnexpectedProcessingError
from services.state import AppState
from services.tasks import background_process


def test_background_process_logs_unexpected_watermark_detail(monkeypatch, caplog, tmp_path):
    task_id = "task-unexpected"
    state = AppState()
    state.create_task(task_id, {"status": "queued", "submitted_at": 0, "progress": 0.0, "stage": "queued"})

    def fake_process_image(*args, **kwargs):
        raise UnexpectedProcessingError(detail="render caption failed")

    monkeypatch.setattr("services.tasks.process_image", fake_process_image)

    logger = logging.getLogger("tests.background_process")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        background_process(
            task_id,
            state,
            str(tmp_path / "sample.jpg"),
            "zh",
            5,
            85,
            "0",
            None,
            {},
            logger,
        )

    task = state.get_task(task_id)
    assert task["status"] == "failed"
    assert task["error"] == "render caption failed"
    assert "render caption failed" in caplog.text
    assert "style=5" in caplog.text
