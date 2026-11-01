import logging
import os
import threading
import time
from types import SimpleNamespace

from constants import AppConstants
from services.cleanup import _cleanup_stale_uploads, start_background_cleaner
from services.state import AppState


def test_cleanup_stale_uploads_keeps_state_db_and_sidecars(tmp_path):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()

    state_db = upload_dir / "app_state.sqlite3"
    state_db.write_text("db", encoding="utf-8")
    state_wal = upload_dir / "app_state.sqlite3-wal"
    state_wal.write_text("wal", encoding="utf-8")
    state_shm = upload_dir / "app_state.sqlite3-shm"
    state_shm.write_text("shm", encoding="utf-8")
    state_lock = upload_dir / "app_state.sqlite3.lock"
    state_lock.write_text("lock", encoding="utf-8")

    stale_image = upload_dir / "old.jpg"
    stale_image.write_text("old-image", encoding="utf-8")

    old_ts = time.time() - 2 * 86400
    for path in (state_db, state_wal, state_shm, state_lock, stale_image):
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
    assert state_lock.exists()


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


def test_cleanup_stale_uploads_keeps_fresh_paired_file(tmp_path):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()

    stale_original = upload_dir / "old.jpg"
    stale_original.write_text("old", encoding="utf-8")
    fresh_watermark = upload_dir / "old_watermark.jpg"
    fresh_watermark.write_text("fresh", encoding="utf-8")

    now = time.time()
    old_ts = now - 2 * 86400
    os.utime(stale_original, (old_ts, old_ts))

    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(upload_dir), "STATE_DB_PATH": None})
    logger = logging.getLogger("tests.cleanup")

    cleaned = _cleanup_stale_uploads(app, now, logger)

    assert cleaned == 1
    assert not stale_original.exists()
    assert fresh_watermark.exists()


def test_cleanup_stale_uploads_does_not_follow_symlinks_outside_root(tmp_path):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"private")
    old_ts = time.time() - 2 * 86400
    os.utime(outside, (old_ts, old_ts))
    (upload_dir / "linked.jpg").symlink_to(outside)
    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(upload_dir), "STATE_DB_PATH": None})

    assert _cleanup_stale_uploads(app, time.time(), logging.getLogger("tests.cleanup")) == 0
    assert outside.read_bytes() == b"private"


def test_background_cleaner_retries_burn_until_deletion_succeeds(tmp_path, monkeypatch):
    state = AppState(str(tmp_path / "state.sqlite3"))
    burned = tmp_path / ".burn_photo.jpg"
    burned.write_bytes(b"private")
    state.schedule_burn(str(burned), time.time() - 1)
    finished = threading.Event()
    attempts = []
    real_remove = os.remove
    real_acknowledge = state.acknowledge_burn_file

    def flaky_remove(path):
        if path == str(burned):
            attempts.append(path)
            if len(attempts) == 1:
                assert str(burned) in state.get_expired_burn_files()
                raise PermissionError("temporarily busy")
        return real_remove(path)

    def acknowledge(path):
        assert not burned.exists()
        real_acknowledge(path)
        finished.set()

    monkeypatch.setattr("services.cleanup.os.remove", flaky_remove)
    monkeypatch.setattr(state, "acknowledge_burn_file", acknowledge)
    monkeypatch.setattr(AppConstants, "CLEANER_INTERVAL_SECONDS", .01)
    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(tmp_path), "STATE_DB_PATH": state.db_path})
    thread = start_background_cleaner(app, state, logging.getLogger("tests.cleanup"))
    try:
        assert finished.wait(2)
        assert len(attempts) == 2
        assert state.get_expired_burn_files() == []
    finally:
        state.shutdown()
    assert not thread.is_alive()


def test_background_cleaner_acknowledges_already_missing_burn(tmp_path, monkeypatch):
    state = AppState(str(tmp_path / "state.sqlite3"))
    missing = str(tmp_path / ".burn_missing.jpg")
    state.schedule_burn(missing, time.time() - 1)
    finished = threading.Event()
    real_acknowledge = state.acknowledge_burn_file

    def acknowledge(path):
        real_acknowledge(path)
        finished.set()

    monkeypatch.setattr(state, "acknowledge_burn_file", acknowledge)
    monkeypatch.setattr(AppConstants, "CLEANER_INTERVAL_SECONDS", .01)
    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(tmp_path), "STATE_DB_PATH": state.db_path})
    thread = start_background_cleaner(app, state, logging.getLogger("tests.cleanup"))
    try:
        assert finished.wait(2)
        assert state.get_expired_burn_files() == []
    finally:
        state.shutdown()
    assert not thread.is_alive()


def test_background_cleaner_keeps_outside_and_protected_burn_targets(tmp_path, monkeypatch):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()
    state = AppState(str(upload_dir / "state.sqlite3"))
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"private")
    state.schedule_burn(str(outside), time.time() - 1)
    state.schedule_burn(state.db_path, time.time() - 1)
    finished = threading.Event()
    real_cleanup = state.cleanup_old_tasks

    def cleanup(now):
        result = real_cleanup(now)
        finished.set()
        return result

    monkeypatch.setattr(state, "cleanup_old_tasks", cleanup)
    monkeypatch.setattr(AppConstants, "CLEANER_INTERVAL_SECONDS", .01)
    app = SimpleNamespace(config={"UPLOAD_FOLDER": str(upload_dir), "STATE_DB_PATH": state.db_path})
    thread = start_background_cleaner(app, state, logging.getLogger("tests.cleanup"))
    try:
        assert finished.wait(2)
        assert outside.read_bytes() == b"private"
        assert os.path.exists(state.db_path)
        assert set(state.get_expired_burn_files()) == {str(outside), state.db_path}
    finally:
        state.shutdown()
    assert not thread.is_alive()
