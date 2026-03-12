import logging

from services.cleanup import run_cleanup_cycle
from services.task_store import get_task, init_db, insert_task, update_task


def test_cleanup_cycle_marks_stale_processing_task_failed(tmp_path):
    db_path = tmp_path / "tasks.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    init_db(str(db_path))
    insert_task(
        str(db_path),
        task_id="stale-task",
        lang="zh",
        watermark_type=1,
        image_quality=100,
        burn_after_read=False,
        logo_preference=None,
        input_path=str(upload_dir / "input.jpg"),
        submitted_at=10.0,
    )
    update_task(
        str(db_path),
        "stale-task",
        status="processing",
        stage="processing",
        started_at=20.0,
        heartbeat_at=30.0,
    )

    summary = run_cleanup_cycle(
        str(upload_dir),
        str(db_path),
        logging.getLogger("tests.cleanup"),
        current_time=30.0 + 6 * 3600 + 1,
    )

    task = get_task(str(db_path), "stale-task")
    assert summary["recovered"] == 1
    assert task["status"] == "failed"
    assert task["stage"] == "failed"
    assert task["error"] == "任务处理中断，请重新上传图片。"
