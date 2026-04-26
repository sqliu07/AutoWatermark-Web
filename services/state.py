from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Optional

from constants import AppConstants


_TASK_COLUMNS = {
    "status",
    "submitted_at",
    "updated_at",
    "progress",
    "stage",
    "result",
    "error",
    "filepath",
    "lang",
    "watermark_type",
    "image_quality",
    "burn_after_read",
    "logo_preference",
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
        self.burn_queue: dict[str, float] = {}
        self.tasks: dict[str, dict[str, Any]] = {}

        self.burn_queue_lock = Lock()
        self.metrics_lock = Lock()
        self.tasks_lock = Lock()
        self.db_lock = Lock()

        self.metrics = _metrics_factory()
        self.executor = _executor_factory()

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._hydrate_from_db()

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
            "lang": row["lang"],
            "watermark_type": row["watermark_type"],
            "image_quality": row["image_quality"],
            "burn_after_read": row["burn_after_read"],
            "logo_preference": row["logo_preference"],
        }
        return task

    def _hydrate_from_db(self) -> None:
        now = time.time()
        task_threshold = now - AppConstants.TASK_RETENTION_SECONDS
        with self.db_lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE submitted_at >= ?",
                (task_threshold,),
            ).fetchall()
            burn_rows = self._conn.execute(
                "SELECT file_path, expire_at FROM burn_queue WHERE expire_at > ?",
                (now,),
            ).fetchall()

        with self.tasks_lock:
            for row in rows:
                self.tasks[row["task_id"]] = self._row_to_task(row)
        with self.burn_queue_lock:
            for row in burn_rows:
                self.burn_queue[row["file_path"]] = row["expire_at"]

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
            "lang": initial_data.get("lang"),
            "watermark_type": initial_data.get("watermark_type"),
            "image_quality": initial_data.get("image_quality"),
            "burn_after_read": initial_data.get("burn_after_read"),
            "logo_preference": initial_data.get("logo_preference"),
        }
        with self.tasks_lock:
            self.tasks[task_id] = dict(payload)

        with self.db_lock:
            self._conn.execute(
                """
                INSERT INTO tasks(
                    task_id, status, submitted_at, updated_at, progress, stage,
                    result_json, error, filepath, lang, watermark_type,
                    image_quality, burn_after_read, logo_preference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    payload["lang"],
                    payload["watermark_type"],
                    payload["image_quality"],
                    payload["burn_after_read"],
                    payload["logo_preference"],
                ),
            )
            self._conn.commit()

    def update_task(self, task_id: str, **fields: Any) -> None:
        allowed_fields = {k: v for k, v in fields.items() if k in _TASK_COLUMNS}
        if not allowed_fields:
            return

        now = time.time()
        allowed_fields["updated_at"] = now

        sql_fields = []
        sql_values = []
        for key, value in allowed_fields.items():
            if key == "result":
                sql_fields.append("result_json = ?")
                sql_values.append(json.dumps(value, ensure_ascii=False) if value is not None else None)
            else:
                sql_fields.append(f"{key} = ?")
                sql_values.append(value)
        sql_values.append(task_id)

        with self.db_lock:
            self._conn.execute(
                f"UPDATE tasks SET {', '.join(sql_fields)} WHERE task_id = ?",
                tuple(sql_values),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        if row is not None:
            task = self._row_to_task(row)
            with self.tasks_lock:
                self.tasks[task_id] = task

    def get_task(self, task_id: str) -> Optional[dict]:
        with self.tasks_lock:
            task = self.tasks.get(task_id)
            if task is not None:
                return dict(task)

        with self.db_lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        task = self._row_to_task(row)
        with self.tasks_lock:
            self.tasks[task_id] = task
        return dict(task)

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
        now = current_time or time.time()
        threshold = now - AppConstants.TASK_RETENTION_SECONDS

        removed_ids: list[str] = []
        with self.tasks_lock:
            for task_id, info in list(self.tasks.items()):
                if now - info.get("submitted_at", 0) > AppConstants.TASK_RETENTION_SECONDS:
                    removed_ids.append(task_id)
                    self.tasks.pop(task_id, None)

        with self.db_lock:
            cursor = self._conn.execute("DELETE FROM tasks WHERE submitted_at < ?", (threshold,))
            self._conn.commit()
            deleted_rows = cursor.rowcount if cursor.rowcount is not None else 0

        return max(len(removed_ids), int(deleted_rows))

    def schedule_burn(self, file_path: str, expire_at: float) -> None:
        with self.burn_queue_lock:
            self.burn_queue[file_path] = expire_at
        with self.db_lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO burn_queue(file_path, expire_at) VALUES (?, ?)",
                (file_path, expire_at),
            )
            self._conn.commit()

    def pop_expired_burn_files(self, current_time: Optional[float] = None) -> list[str]:
        now = current_time or time.time()
        expired: list[str] = []
        with self.burn_queue_lock:
            for file_path, expire_at in list(self.burn_queue.items()):
                if now > expire_at:
                    expired.append(file_path)
                    self.burn_queue.pop(file_path, None)

        if expired:
            placeholders = ",".join(["?"] * len(expired))
            with self.db_lock:
                self._conn.execute(
                    f"DELETE FROM burn_queue WHERE file_path IN ({placeholders})",
                    tuple(expired),
                )
                self._conn.commit()
        return expired

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait)
        with self.db_lock:
            self._conn.close()
