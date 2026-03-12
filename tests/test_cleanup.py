import sqlite3
import logging

from infra.sqlite_task_store import get_task, init_db, insert_task, update_task
from services.cleanup import run_cleanup_cycle


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


def test_init_db_migrates_legacy_tasks_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0.0,
                stage TEXT NOT NULL DEFAULT 'queued',
                lang TEXT NOT NULL,
                watermark_type INTEGER NOT NULL,
                image_quality INTEGER NOT NULL,
                logo_preference TEXT,
                burn_after_read INTEGER NOT NULL DEFAULT 0,
                input_path TEXT NOT NULL,
                output_path TEXT,
                result_url TEXT,
                error TEXT,
                submitted_at REAL NOT NULL,
                started_at REAL,
                finished_at REAL
            );
            """
        )

    init_db(str(db_path))

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
    assert "heartbeat_at" in columns
