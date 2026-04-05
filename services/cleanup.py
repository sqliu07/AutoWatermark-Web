import glob
import os
import tempfile
import threading
import time

from constants import AppConstants


def cleanup_file_and_original(file_path: str, logger) -> None:
    """Delete a single file if it exists."""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info("[Burn] Deleted: %s", os.path.basename(file_path))
        except OSError:
            pass


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
            zip_pattern = os.path.join(temp_dir, "Packed_Watermark_Images_*.zip")
            for zip_file in glob.glob(zip_pattern):
                try:
                    if current_time - os.path.getmtime(zip_file) > AppConstants.ZIP_RETENTION_SECONDS:
                        os.remove(zip_file)
                        logger.info("[Auto-Clean] Deleted old zip: %s", zip_file)
                        cleaned_zip += 1
                except OSError:
                    pass

            # 3) Stale uploads in upload folder
            upload_dir = app.config["UPLOAD_FOLDER"]
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
