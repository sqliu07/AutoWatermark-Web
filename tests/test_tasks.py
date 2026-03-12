import logging

from core.errors import UnexpectedProcessingError
from infra.sqlite_task_store import get_task, init_db, insert_task
from services.tasks import background_process


def test_background_process_logs_unexpected_watermark_detail(monkeypatch, caplog, tmp_path):
    task_id = "task-unexpected"
    db_path = tmp_path / "tasks.db"
    init_db(str(db_path))
    insert_task(
        str(db_path),
        task_id=task_id,
        lang="zh",
        watermark_type=5,
        image_quality=85,
        burn_after_read=False,
        logo_preference=None,
        input_path=str(tmp_path / "sample.jpg"),
        submitted_at=0,
    )

    def fake_process_image(*args, **kwargs):
        raise UnexpectedProcessingError(detail="render caption failed")

    monkeypatch.setattr("services.tasks.process_image", fake_process_image)

    logger = logging.getLogger("tests.background_process")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        background_process(
            task_id,
            str(db_path),
            str(tmp_path / "sample.jpg"),
            "zh",
            5,
            85,
            "0",
            None,
            {},
            logger,
        )

    task = get_task(str(db_path), task_id)
    assert task["status"] == "failed"
    assert task["error"] == "render caption failed"
    assert "render caption failed" in caplog.text
    assert "style=5" in caplog.text
