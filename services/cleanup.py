from __future__ import annotations

import glob
import os
import tempfile
import threading
import time
from typing import Optional

from config.constants import AppConstants
from infra.sqlite_task_store import (
    delete_finished_tasks_older_than,
    list_stale_processing_tasks,
    pop_expired_burn_files,
    update_task,
)
from services.i18n import get_common_message


def cleanup_file_and_original(file_path: str, logger) -> None:
    """Delete a single file if it exists."""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info("[Burn] Deleted: %s", os.path.basename(file_path))
        except OSError:
            pass


def run_cleanup_cycle(upload_dir: str, db_path: str, logger, current_time: Optional[float] = None) -> dict[str, int]:
    current_time = current_time or time.time()
    cleaned_burn = 0
    cleaned_zip = 0
    cleaned_stale = 0
    cleaned_tasks = 0
    recovered_tasks = 0

    # 1) Burn queue cleanup
    for fp in pop_expired_burn_files(db_path, current_time):
        cleanup_file_and_original(fp, logger)
        cleaned_burn += 1

    # 2) Mark stale processing tasks as failed
    stale_cutoff = current_time - AppConstants.TASK_HEARTBEAT_TIMEOUT_SECONDS
    for task in list_stale_processing_tasks(db_path, stale_cutoff):
        update_task(
            db_path,
            task["task_id"],
            status="failed",
            stage="failed",
            progress=1.0,
            error=get_common_message("task_interrupted", task["lang"]),
            finished_at=current_time,
        )
        recovered_tasks += 1

    # 3) Completed task cleanup
    cleaned_tasks = delete_finished_tasks_older_than(
        db_path,
        current_time - AppConstants.TASK_RETENTION_SECONDS,
    )

    # 4) Stale zip files in temp dir
    temp_dir = tempfile.gettempdir()
    zip_pattern = os.path.join(temp_dir, "Packed_Watermark_Images_*.zip")
    for zip_file in glob.glob(zip_pattern):
        try:
            if current_time - os.path.getmtime(zip_file) > AppConstants.ZIP_RETENTION_SECONDS:
                os.remove(zip_file)
                logger.info("[Auto-Clean] Deleted old zip: %s", zip_file)
                cleaned_zip += 1
        except OSError:
            pass

    # 5) Stale uploads in upload folder
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        try:
            if (
                os.path.isfile(file_path)
                and (current_time - os.path.getmtime(file_path) > AppConstants.UPLOAD_RETENTION_SECONDS)
            ):
                os.remove(file_path)
                logger.info("[Auto-Clean] Deleted stale file: %s", filename)
                cleaned_stale += 1
        except OSError:
            pass

    return {
        "burn": cleaned_burn,
        "recovered": recovered_tasks,
        "tasks": cleaned_tasks,
        "zip": cleaned_zip,
        "stale": cleaned_stale,
    }


def start_background_cleaner(app, db_path: str, logger) -> threading.Thread:
    """Start background cleanup worker for burn queue, zip temp files, and stale uploads."""

    def background_cleaner() -> None:
        while True:
            time.sleep(AppConstants.CLEANER_INTERVAL_SECONDS)
            summary = run_cleanup_cycle(app.config["UPLOAD_FOLDER"], db_path, logger)

            if any(summary.values()):
                logger.info(
                    "[Auto-Clean] Summary - burn: %s, recovered: %s, tasks: %s, zip: %s, stale: %s",
                    summary["burn"],
                    summary["recovered"],
                    summary["tasks"],
                    summary["zip"],
                    summary["stale"],
                )

    thread = threading.Thread(target=background_cleaner, daemon=True)
    thread.start()
    return thread
