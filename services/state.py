from __future__ import annotations

import json
import os
import fcntl
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from typing import Any, Optional

from constants import AppConstants
from services.filenames import download_name


_TASK_COLUMNS = {
    "status",
    "submitted_at",
    "updated_at",
    "progress",
    "stage",
    "result",
    "error",
    "filepath",
    "original_name",
    "lang",
    "watermark_type",
    "image_quality",
    "burn_after_read",
    "logo_preference",
    "features",
    "preliminary_manufacturer",
    "preserve_motion",
    "preserve_hdr",
}

_OPTION_COLUMNS = {
    "original_name": "TEXT",
    "features_json": "TEXT",
    "preliminary_manufacturer": "TEXT",
    "preserve_motion": "INTEGER",
    "preserve_hdr": "INTEGER",
}


def _executor_factory() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=AppConstants.EXECUTOR_MAX_WORKERS)


def _metrics_factory() -> dict:
    return {
        "total_tasks": 0,
        "succeeded_tasks": 0,
        "failed_tasks": 0,
    }


class AppState:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.metrics_lock = Lock()
        self.db_lock = Lock()

        self.stop_event = Event()
        self.cleaner_thread = None
        self._shutdown_lock = Lock()
        self._closed = False
        self._admission_lock = Lock()
        self._pending_jobs = 0
        self._pending_bytes = 0
        self.upload_lock = Lock()
        self.owner_pid = os.getpid()
        # Exclusive process ownership also protects restart recovery. Do not unlink
        # this file: an existing inode must remain the lock target for all owners.
        self._owner_file = open(self.db_path + ".lock", "a+b")
        try:
            fcntl.flock(self._owner_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._owner_file.close()
            raise RuntimeError("Task database already in use; run a single worker without preload") from exc

        self.metrics = _metrics_factory()
        self.executor = _executor_factory()

        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_db()
            self._hydrate_from_db()
        except BaseException:
            if hasattr(self, "_conn"):
                self._conn.close()
            self.executor.shutdown()
            self._owner_file.close()
            raise

    def _init_db(self) -> None:
        with self.db_lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    submitted_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    progress REAL NOT NULL DEFAULT 0.0,
                    stage TEXT,
                    result_json TEXT,
                    error TEXT,
                    filepath TEXT,
                    lang TEXT,
                    watermark_type INTEGER,
                    image_quality INTEGER,
                    burn_after_read TEXT,
                    logo_preference TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_submitted_at ON tasks(submitted_at)"
            )
            existing_columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
            for column, column_type in _OPTION_COLUMNS.items():
                if column not in existing_columns:
                    self._conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} {column_type}")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_filepath ON tasks(filepath)")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS burn_queue (
                    file_path TEXT PRIMARY KEY,
                    expire_at REAL NOT NULL
                )
                """
            )
            self._conn.commit()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
        result_json = row["result_json"]
        task = {
            "status": row["status"],
            "submitted_at": row["submitted_at"],
            "updated_at": row["updated_at"],
            "progress": row["progress"],
            "stage": row["stage"],
            "result": json.loads(result_json) if result_json else None,
            "error": row["error"],
            "filepath": row["filepath"],
            "original_name": row["original_name"],
            "lang": row["lang"],
            "watermark_type": row["watermark_type"],
            "image_quality": row["image_quality"],
            "burn_after_read": row["burn_after_read"],
            "logo_preference": row["logo_preference"],
            "features": json.loads(row["features_json"]) if row["features_json"] else None,
            "preliminary_manufacturer": row["preliminary_manufacturer"],
            "preserve_motion": None if row["preserve_motion"] is None else bool(row["preserve_motion"]),
            "preserve_hdr": None if row["preserve_hdr"] is None else bool(row["preserve_hdr"]),
        }
        return task

    def _hydrate_from_db(self) -> None:
        # Recovery is safe only after acquiring exclusive database ownership.
        # Waiting for user choices is durable and does not imply interrupted work.
        with self.db_lock:
            self._conn.execute(
                "UPDATE tasks SET status = 'failed', error = ?, stage = 'failed', "
                "progress = 1.0, updated_at = ? WHERE status IN ('queued', 'processing')",
                ("服务重启导致任务中断", time.time()),
            )
            self._conn.commit()

    def create_task(self, task_id: str, initial_data: dict) -> None:
        now = time.time()
        payload = {
            "status": initial_data.get("status", "queued"),
            "submitted_at": initial_data.get("submitted_at", now),
            "updated_at": now,
            "progress": initial_data.get("progress", 0.0),
            "stage": initial_data.get("stage", "queued"),
            "result": initial_data.get("result"),
            "error": initial_data.get("error"),
            "filepath": initial_data.get("filepath"),
            "original_name": initial_data.get("original_name"),
            "lang": initial_data.get("lang"),
            "watermark_type": initial_data.get("watermark_type"),
            "image_quality": initial_data.get("image_quality"),
            "burn_after_read": initial_data.get("burn_after_read"),
            "logo_preference": initial_data.get("logo_preference"),
            "features": initial_data.get("features"),
            "preliminary_manufacturer": initial_data.get("preliminary_manufacturer"),
            "preserve_motion": initial_data.get("preserve_motion"),
            "preserve_hdr": initial_data.get("preserve_hdr"),
        }
        with self.db_lock:
            self._conn.execute(
                """
                INSERT INTO tasks(
                    task_id, status, submitted_at, updated_at, progress, stage,
                    result_json, error, filepath, original_name, lang, watermark_type,
                    image_quality, burn_after_read, logo_preference,
                    features_json, preliminary_manufacturer, preserve_motion, preserve_hdr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    payload["status"],
                    payload["submitted_at"],
                    payload["updated_at"],
                    payload["progress"],
                    payload["stage"],
                    json.dumps(payload["result"], ensure_ascii=False) if payload["result"] is not None else None,
                    payload["error"],
                    payload["filepath"],
                    payload["original_name"],
                    payload["lang"],
                    payload["watermark_type"],
                    payload["image_quality"],
                    payload["burn_after_read"],
                    payload["logo_preference"],
                    json.dumps(payload["features"], ensure_ascii=False) if payload["features"] is not None else None,
                    payload["preliminary_manufacturer"],
                    None if payload["preserve_motion"] is None else int(bool(payload["preserve_motion"])),
                    None if payload["preserve_hdr"] is None else int(bool(payload["preserve_hdr"])),
                ),
            )
            self._conn.commit()

    def update_task(self, task_id: str, *, expected_status: str | None = None, **fields: Any) -> bool:
        allowed_fields = {k: v for k, v in fields.items() if k in _TASK_COLUMNS}
        if not allowed_fields:
            return False

        now = time.time()
        allowed_fields["updated_at"] = now

        sql_fields = []
        sql_values = []
        for key, value in allowed_fields.items():
            if key == "result":
                sql_fields.append("result_json = ?")
                sql_values.append(json.dumps(value, ensure_ascii=False) if value is not None else None)
            elif key == "features":
                sql_fields.append("features_json = ?")
                sql_values.append(json.dumps(value, ensure_ascii=False) if value is not None else None)
            elif key in {"preserve_motion", "preserve_hdr"}:
                sql_fields.append(f"{key} = ?")
                sql_values.append(None if value is None else int(bool(value)))
            else:
                sql_fields.append(f"{key} = ?")
                sql_values.append(value)
        sql_values.append(task_id)

        where = "task_id = ?"
        if expected_status is not None:
            where += " AND status = ?"
            sql_values.append(expected_status)
        with self.db_lock:
            cursor = self._conn.execute(
                f"UPDATE tasks SET {', '.join(sql_fields)} WHERE {where}", tuple(sql_values),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def get_task(self, task_id: str) -> Optional[dict]:
        with self.db_lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row is not None else None

    def count_tasks_by_status(self, *statuses: str) -> int:
        if not statuses:
            return 0
        placeholders = ",".join(["?"] * len(statuses))
        with self.db_lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS cnt FROM tasks WHERE status IN ({placeholders})",
                tuple(statuses),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def cleanup_old_tasks(self, current_time: Optional[float] = None) -> int:
        now = time.time() if current_time is None else current_time
        with self.db_lock:
            # Abandoned prompts have no running executor; expire them separately.
            self._conn.execute(
                "UPDATE tasks SET status='failed', stage='failed', error=?, updated_at=? "
                "WHERE status IN ('needs_logo', 'needs_options') AND updated_at < ?",
                ("等待选择超时，请重试", now, now - AppConstants.TASK_RETENTION_SECONDS),
            )
            cursor = self._conn.execute(
                "DELETE FROM tasks WHERE status IN ('succeeded', 'failed', 'cancelled') AND updated_at < ?",
                (now - AppConstants.TASK_RETENTION_SECONDS,),
            )
            self._conn.commit()
            return cursor.rowcount

    def active_filepaths(self) -> set[str]:
        with self.db_lock:
            rows = self._conn.execute(
                "SELECT filepath FROM tasks WHERE status IN ('queued','processing','needs_logo','needs_options')"
            ).fetchall()
        return {os.path.realpath(row[0]) for row in rows if row[0]}

    def get_burn_original(self, output_path: str) -> Optional[str]:
        with self.db_lock:
            rows = self._conn.execute(
                "SELECT filepath FROM tasks WHERE status='succeeded' AND burn_after_read='1'"
            ).fetchall()
        output_path = os.path.realpath(output_path)
        for row in rows:
            if not row[0]:
                continue
            original = os.path.realpath(row[0])
            stem, extension = os.path.splitext(original)
            if original != output_path and stem + "_watermark" + extension == output_path:
                return original
        return None

    def get_download_name(self, output_path: str) -> str:
        output_path = os.path.realpath(output_path)
        stem, extension = os.path.splitext(output_path)
        if not stem.endswith("_watermark"):
            return os.path.basename(output_path)
        original_path = stem[:-len("_watermark")] + extension
        with self.db_lock:
            row = self._conn.execute(
                "SELECT original_name FROM tasks WHERE filepath=? AND status='succeeded' "
                "ORDER BY updated_at DESC LIMIT 1", (original_path,),
            ).fetchone()
        return download_name(row[0] if row else None, output_path)

    def schedule_burn(self, file_path: str, expire_at: float) -> None:
        with self.db_lock:
            self._conn.execute(
                "INSERT INTO burn_queue(file_path, expire_at) VALUES (?, ?) "
                "ON CONFLICT(file_path) DO UPDATE SET expire_at=MIN(expire_at, excluded.expire_at)",
                (file_path, expire_at),
            )
            self._conn.commit()

    def get_expired_burn_files(self, current_time: Optional[float] = None) -> list[str]:
        now = time.time() if current_time is None else current_time
        with self.db_lock:
            rows = self._conn.execute("SELECT file_path FROM burn_queue WHERE expire_at <= ?", (now,)).fetchall()
        return [row[0] for row in rows]

    def acknowledge_burn_file(self, file_path: str) -> None:
        with self.db_lock:
            self._conn.execute("DELETE FROM burn_queue WHERE file_path = ?", (file_path,))
            self._conn.commit()

    def submit(self, fn, payload):
        from werkzeug.exceptions import ServiceUnavailable
        size = os.path.getsize(payload.filepath)
        with self._admission_lock:
            if (self.stop_event.is_set() or self._pending_jobs >= AppConstants.MAX_PENDING_TASKS
                    or self._pending_bytes + size > AppConstants.MAX_PENDING_BYTES):
                raise ServiceUnavailable("Task capacity reached; try again later")
            self._pending_jobs += 1
            self._pending_bytes += size

        def release(_future=None):
            with self._admission_lock:
                self._pending_jobs -= 1
                self._pending_bytes -= size
        try:
            future = self.executor.submit(fn, payload)
        except BaseException:
            release()
            raise
        future.add_done_callback(release)
        return future

    def shutdown(self, wait: bool = True) -> None:
        # Closing the database while a task is still writing is never safe.
        if not wait:
            raise ValueError("shutdown requires wait=True to drain database users")
        with self._shutdown_lock:
            if self._closed:
                return
            self.stop_event.set()
            if self.cleaner_thread is not None:
                self.cleaner_thread.join()
            self.executor.shutdown(wait=True)
            with self.db_lock:
                self._conn.close()
            self._owner_file.close()
            self._closed = True
