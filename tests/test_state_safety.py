import io
import signal
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from werkzeug.datastructures import FileStorage

from constants import AppConstants
from services.state import AppState
from services.upload_workflow import _save_upload


def test_uploads_never_share_a_path(tmp_path, monkeypatch):
    monkeypatch.setattr(time, 'time', lambda: 1000)
    a = _save_upload(FileStorage(io.BytesIO(b'A'), filename='same.jpg'), str(tmp_path))
    b = _save_upload(FileStorage(io.BytesIO(b'B'), filename='same.jpg'), str(tmp_path))
    assert a != b
    assert open(a, 'rb').read() == b'A'
    assert open(b, 'rb').read() == b'B'


def test_only_one_owner_can_recover_a_database(tmp_path):
    path = str(tmp_path / 'state.db')
    state = AppState(path)
    try:
        state.create_task('active', {'status': 'processing'})
        with pytest.raises(RuntimeError, match='already in use'):
            AppState(path)
        assert state.get_task('active')['status'] == 'processing'
    finally:
        state.shutdown()
    recovered = AppState(path)
    try:
        assert recovered.get_task('active')['status'] == 'failed'
    finally:
        recovered.shutdown()


def test_reads_do_not_return_stale_cached_state(tmp_path):
    state = AppState(str(tmp_path / 'state.db'))
    try:
        state.create_task('j', {'status': 'queued'})
        assert state.get_task('j')['status'] == 'queued'
        with sqlite3.connect(state.db_path) as conn:
            conn.execute("UPDATE tasks SET status='succeeded' WHERE task_id='j'")
        assert state.get_task('j')['status'] == 'succeeded'
    finally:
        state.shutdown()


def test_task_transition_has_exactly_one_winner(tmp_path):
    state = AppState(str(tmp_path / 'state.db'))
    try:
        state.create_task('j', {'status': 'failed'})
        barrier = threading.Barrier(2)
        def claim():
            barrier.wait(timeout=2)
            return state.update_task('j', expected_status='failed', status='queued')
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(claim) for _ in range(2)]
            assert sorted(f.result(timeout=3) for f in futures) == [False, True]
    finally:
        state.shutdown()


def test_cleanup_keeps_active_and_recently_retried_tasks(tmp_path):
    state = AppState(str(tmp_path / 'state.db'))
    now = time.time()
    try:
        for task_id, status in [('active', 'processing'), ('queued', 'queued'), ('done', 'succeeded')]:
            state.create_task(task_id, {'status': status, 'submitted_at': now - 7200})
        state.update_task('done', status='succeeded')
        assert state.cleanup_old_tasks(now + 1) == 0
        assert state.cleanup_old_tasks(now + 7200) == 1
        assert state.get_task('active') is not None
        assert state.get_task('queued') is not None
    finally:
        state.shutdown()


def test_expired_burn_survives_restart_until_acknowledged(tmp_path):
    path = str(tmp_path / 'state.db')
    state = AppState(path)
    state.schedule_burn('/tmp/test-burn', time.time() - 1)
    state.shutdown()
    state = AppState(path)
    try:
        assert state.get_expired_burn_files() == ['/tmp/test-burn']
        assert state.get_expired_burn_files() == ['/tmp/test-burn']
        state.acknowledge_burn_file('/tmp/test-burn')
        assert state.get_expired_burn_files() == []
    finally:
        state.shutdown()


def test_factory_keeps_server_signal_handler(tmp_path):
    from app_factory import create_app
    handler = signal.getsignal(signal.SIGTERM)
    app = create_app({'UPLOAD_FOLDER': str(tmp_path), 'START_BACKGROUND_CLEANER': False})
    try:
        assert signal.getsignal(signal.SIGTERM) == handler
    finally:
        # Restore it even when testing the buggy implementation.
        signal.signal(signal.SIGTERM, handler)
        app.extensions['state'].shutdown()


def test_factory_rejects_multiworker_before_initializing_database(tmp_path, monkeypatch):
    from app_factory import create_app
    monkeypatch.setenv('GUNICORN_WORKERS', '2')
    with pytest.raises(RuntimeError, match='single worker'):
        create_app({'UPLOAD_FOLDER': str(tmp_path)})


def test_cleaner_recovers_and_stops_before_database_close(tmp_path, monkeypatch):
    from services.cleanup import start_background_cleaner
    import logging
    from types import SimpleNamespace
    state = AppState(str(tmp_path / 'state.db'))
    recovered = threading.Event()
    calls = []
    real_cleanup = state.cleanup_old_tasks
    def flaky_cleanup(now):
        calls.append(now)
        if len(calls) == 1:
            raise sqlite3.OperationalError('database is locked')
        recovered.set()
        return real_cleanup(now)
    monkeypatch.setattr(state, 'cleanup_old_tasks', flaky_cleanup)
    monkeypatch.setattr(AppConstants, 'CLEANER_INTERVAL_SECONDS', .01)
    app = SimpleNamespace(config={'UPLOAD_FOLDER': str(tmp_path), 'STATE_DB_PATH': state.db_path})
    thread = start_background_cleaner(app, state, logging.getLogger('test-cleaner'))
    try:
        assert recovered.wait(2)
    finally:
        state.shutdown()
    assert not thread.is_alive()
    state.shutdown()  # idempotent
