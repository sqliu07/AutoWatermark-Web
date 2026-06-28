import glob
import os
import re
import tempfile
import threading
import time

from constants import AppConstants

_WATERMARK_SUFFIX = "_watermark"
_WATERMARK_PATTERN = re.compile(r"(.+)_watermark(\.[^.]+)$")


def _derive_paired_path(file_path: str) -> str | None:
    """根据 _watermark 命名规则推导配对文件路径。"""
    dirname = os.path.dirname(file_path)
    basename = os.path.basename(file_path)
    m = _WATERMARK_PATTERN.match(basename)
    if m:
        # foo_watermark.jpg → foo.jpg
        return os.path.join(dirname, m.group(1) + m.group(2))
    # foo.jpg → foo_watermark.jpg
    root, ext = os.path.splitext(basename)
    return os.path.join(dirname, f"{root}{_WATERMARK_SUFFIX}{ext}")


def cleanup_file_and_original(file_path: str, logger) -> None:
    """Delete a single file if it exists."""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info("[Burn] Deleted: %s", os.path.basename(file_path))
        except OSError:
            pass


def _protected_upload_files(app) -> set[str]:
    protected: set[str] = set()
    state_db_path = app.config.get("STATE_DB_PATH")
    if not state_db_path:
        return protected

    db_real = os.path.realpath(state_db_path)
    protected.add(db_real)
    protected.add(db_real + "-wal")
    protected.add(db_real + "-shm")
    protected.add(db_real + "-journal")
    return protected


def _is_stale_upload_file(file_path: str, current_time: float, protected: set[str]) -> bool:
    return (
        file_path not in protected
        and os.path.isfile(file_path)
        and (current_time - os.path.getmtime(file_path) > AppConstants.UPLOAD_RETENTION_SECONDS)
    )


def _delete_stale_upload(file_path: str, logger) -> bool:
    try:
        os.remove(file_path)
        logger.info("[Auto-Clean] Deleted stale file: %s", os.path.basename(file_path))
        return True
    except OSError:
        return False


def _cleanup_stale_uploads(app, current_time: float, logger) -> int:
    upload_dir = app.config["UPLOAD_FOLDER"]
    if not os.path.isdir(upload_dir):
        return 0

    protected = _protected_upload_files(app)
    cleaned_stale = 0

    for filename in os.listdir(upload_dir):
        file_path = os.path.realpath(os.path.join(upload_dir, filename))
        if file_path in protected:
            continue

        try:
            if _is_stale_upload_file(file_path, current_time, protected):
                paired = _derive_paired_path(file_path)
                if _delete_stale_upload(file_path, logger):
                    cleaned_stale += 1
                if paired and _is_stale_upload_file(paired, current_time, protected):
                    if _delete_stale_upload(paired, logger):
                        cleaned_stale += 1
        except OSError:
            pass

    return cleaned_stale


def start_background_cleaner(app, state, logger) -> threading.Thread:
    """Start background cleanup worker for burn queue, zip temp files, and stale uploads."""

    def background_cleaner() -> None:
        while True:
            time.sleep(AppConstants.CLEANER_INTERVAL_SECONDS)
            current_time = time.time()

            cleaned_burn = 0
            cleaned_zip = 0
            cleaned_stale = 0

            # 1) Burn queue cleanup
            expired_burn_files = state.pop_expired_burn_files(current_time)
            for fp in expired_burn_files:
                cleanup_file_and_original(fp, logger)
                cleaned_burn += 1

            # 2) Stale zip files in temp dir
            temp_dir = tempfile.gettempdir()
            zip_pattern = os.path.join(temp_dir, "watermark_*.zip")
            for zip_file in glob.glob(zip_pattern):
                try:
                    if current_time - os.path.getmtime(zip_file) > AppConstants.ZIP_RETENTION_SECONDS:
                        os.remove(zip_file)
                        logger.info("[Auto-Clean] Deleted old zip: %s", zip_file)
                        cleaned_zip += 1
                except OSError:
                    pass

            # 3) Stale uploads in upload folder
            cleaned_stale = _cleanup_stale_uploads(app, current_time, logger)

            # 4) Stale tasks in memory
            cleaned_tasks = state.cleanup_old_tasks(current_time)

            if cleaned_burn or cleaned_zip or cleaned_stale or cleaned_tasks:
                logger.info(
                    "[Auto-Clean] Summary - burn: %s, zip: %s, stale: %s, tasks: %s",
                    cleaned_burn,
                    cleaned_zip,
                    cleaned_stale,
                    cleaned_tasks,
                )

    thread = threading.Thread(target=background_cleaner, daemon=True)
    thread.start()
    return thread
