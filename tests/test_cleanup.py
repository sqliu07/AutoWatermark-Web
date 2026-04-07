import logging
import os
import time
from types import SimpleNamespace

from services.cleanup import _cleanup_stale_uploads


def test_cleanup_stale_uploads_keeps_state_db_and_sidecars(tmp_path):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()

    state_db = upload_dir / "app_state.sqlite3"
    state_db.write_text("db", encoding="utf-8")
    state_wal = upload_dir / "app_state.sqlite3-wal"
    state_wal.write_text("wal", encoding="utf-8")
    state_shm = upload_dir / "app_state.sqlite3-shm"
    state_shm.write_text("shm", encoding="utf-8")

    stale_image = upload_dir / "old.jpg"
    stale_image.write_text("old-image", encoding="utf-8")

    old_ts = time.time() - 2 * 86400
    for path in (state_db, state_wal, state_shm, stale_image):
        os.utime(path, (old_ts, old_ts))

    app = SimpleNamespace(
        config={
            "UPLOAD_FOLDER": str(upload_dir),
            "STATE_DB_PATH": str(state_db),
        }
    )
    logger = logging.getLogger("tests.cleanup")

    cleaned = _cleanup_stale_uploads(app, time.time(), logger)

    assert cleaned == 1
    assert not stale_image.exists()
    assert state_db.exists()
    assert state_wal.exists()
    assert state_shm.exists()


def test_cleanup_stale_uploads_without_state_db_path(tmp_path):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()

    stale_file = upload_dir / "old.png"
    stale_file.write_text("old", encoding="utf-8")
    old_ts = time.time() - 2 * 86400
    os.utime(stale_file, (old_ts, old_ts))

    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(upload_dir), "STATE_DB_PATH": None})
    logger = logging.getLogger("tests.cleanup")

    cleaned = _cleanup_stale_uploads(app, time.time(), logger)

    assert cleaned == 1
    assert not stale_file.exists()
