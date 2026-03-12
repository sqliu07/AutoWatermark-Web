from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from typing import Any, Dict, Optional


_TASK_FIELDS = {
    "status",
    "progress",
    "stage",
    "error",
    "started_at",
    "finished_at",
    "result_url",
    "output_path",
    "heartbeat_at",
}


def _ensure_parent_dir(db_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _connect(db_path: str) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: str) -> None:
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
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
                finished_at REAL,
                heartbeat_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_finished_at ON tasks(finished_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_output_path ON tasks(output_path);
            CREATE INDEX IF NOT EXISTS idx_tasks_heartbeat_at ON tasks(heartbeat_at);

            CREATE TABLE IF NOT EXISTS burn_files (
                file_path TEXT PRIMARY KEY,
                expire_at REAL NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_burn_files_expire_at ON burn_files(expire_at);
            """
        )
        _ensure_column(conn, "tasks", "heartbeat_at", "ALTER TABLE tasks ADD COLUMN heartbeat_at REAL")


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any(row["name"] == column_name for row in rows):
        return
    conn.execute(ddl)


def insert_task(
    db_path: str,
    *,
    task_id: str,
    lang: str,
    watermark_type: int,
    image_quality: int,
    burn_after_read: bool,
    logo_preference: Optional[str],
    input_path: str,
    submitted_at: float,
) -> None:
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            """
            INSERT INTO tasks (
                task_id,
                status,
                progress,
                stage,
                lang,
                watermark_type,
                image_quality,
                logo_preference,
                burn_after_read,
                input_path,
                submitted_at,
                heartbeat_at
            ) VALUES (?, 'queued', 0.0, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                lang,
                watermark_type,
                image_quality,
                logo_preference,
                1 if burn_after_read else 0,
                input_path,
                submitted_at,
                submitted_at,
            ),
        )


def update_task(db_path: str, task_id: str, **fields: Any) -> None:
    updates = {key: value for key, value in fields.items() if key in _TASK_FIELDS}
    if not updates:
        return
    updates.setdefault("heartbeat_at", time.time())

    columns = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [task_id]

    with closing(_connect(db_path)) as conn, conn:
        conn.execute(f"UPDATE tasks SET {columns} WHERE task_id = ?", values)


def get_task(db_path: str, task_id: str) -> Optional[Dict[str, Any]]:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT
                task_id,
                status,
                progress,
                stage,
                error,
                result_url,
                submitted_at,
                started_at,
                finished_at
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

    if row is None:
        return None

    task = {
        "status": row["status"],
        "progress": row["progress"],
        "stage": row["stage"],
        "submitted_at": row["submitted_at"],
    }
    if row["error"]:
        task["error"] = row["error"]
    if row["result_url"]:
        task["result"] = {"processed_image": row["result_url"]}
    if row["started_at"] is not None:
        task["started_at"] = row["started_at"]
    if row["finished_at"] is not None:
        task["finished_at"] = row["finished_at"]
    return task


def count_tasks_by_status(db_path: str, *statuses: str) -> int:
    if not statuses:
        return 0

    placeholders = ", ".join("?" for _ in statuses)
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS count FROM tasks WHERE status IN ({placeholders})",
            statuses,
        ).fetchone()
    return int(row["count"]) if row is not None else 0


def get_task_stats(db_path: str) -> Dict[str, int]:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_tasks
            FROM tasks
            """
        ).fetchone()

    return {
        "total_tasks": int(row["total_tasks"] or 0),
        "failed_tasks": int(row["failed_tasks"] or 0),
    }


def delete_finished_tasks_older_than(db_path: str, cutoff_time: float) -> int:
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute(
            """
            DELETE FROM tasks
            WHERE status IN ('succeeded', 'failed')
              AND COALESCE(finished_at, submitted_at) < ?
            """,
            (cutoff_time,),
        )
        return cursor.rowcount


def list_stale_processing_tasks(db_path: str, cutoff_time: float) -> list[Dict[str, Any]]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT task_id, lang
            FROM tasks
            WHERE status = 'processing'
              AND COALESCE(heartbeat_at, started_at, submitted_at) < ?
            """,
            (cutoff_time,),
        ).fetchall()
    return [{"task_id": row["task_id"], "lang": row["lang"]} for row in rows]


def schedule_burn_file(db_path: str, file_path: str, expire_at: float, created_at: float) -> None:
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            """
            INSERT INTO burn_files (file_path, expire_at, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET expire_at = excluded.expire_at
            """,
            (file_path, expire_at, created_at),
        )


def pop_expired_burn_files(db_path: str, current_time: float) -> list[str]:
    with closing(_connect(db_path)) as conn, conn:
        rows = conn.execute(
            "SELECT file_path FROM burn_files WHERE expire_at <= ?",
            (current_time,),
        ).fetchall()
        if not rows:
            return []

        file_paths = [row["file_path"] for row in rows]
        conn.executemany(
            "DELETE FROM burn_files WHERE file_path = ?",
            ((file_path,) for file_path in file_paths),
        )
        return file_paths


def is_file_scheduled_for_burn(db_path: str, file_path: str) -> bool:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT 1 FROM burn_files WHERE file_path = ?",
            (file_path,),
        ).fetchone()
    return row is not None
