import os
import time
import uuid
from typing import Optional, Set

from PIL import Image
import piexif

from constants import CommonConstants, AppConstants
from errors import WatermarkError
from exif_utils import get_manufacturer
from process import process_image
from services.i18n import get_common_message


def allowed_file(filename: str, allowed_extensions: Set[str]) -> bool:
    """Check allowed file extensions."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def cleanup_old_tasks(state) -> None:
    """Remove tasks older than retention window."""
    current_time = time.time()
    to_remove = []
    with state.tasks_lock:
        for tid, info in list(state.tasks.items()):
            if current_time - info.get("submitted_at", 0) > AppConstants.TASK_RETENTION_SECONDS:
                to_remove.append(tid)
        for tid in to_remove:
            state.tasks.pop(tid, None)


def detect_manufacturer(filepath: str):
    try:
        with Image.open(filepath) as image:
            exif_bytes = image.info.get("exif")
            if not exif_bytes:
                return None
            exif_dict = piexif.load(exif_bytes)
            return get_manufacturer(filepath, exif_dict)
    except Exception:
        return None


def normalize_image_quality(image_quality: str) -> int:
    if image_quality == "high":
        return CommonConstants.IMAGE_QUALITY_MAP.get("high")
    if image_quality == "medium":
        return CommonConstants.IMAGE_QUALITY_MAP.get("medium")
    return CommonConstants.IMAGE_QUALITY_MAP.get("low")


def _update_queue_metrics(state, task_id: str, logger) -> None:
    with state.metrics_lock:
        state.metrics["total_tasks"] += 1
        total = state.metrics["total_tasks"]
        failed = state.metrics["failed_tasks"]
    failure_rate = (failed / total) if total else 0
    with state.tasks_lock:
        queue_length = sum(1 for info in state.tasks.values() if info.get("status") == "queued")
    logger.info(
        "Queued task %s | queue=%s | failure_rate=%.2f%%",
        task_id,
        queue_length,
        failure_rate * 100,
    )


def create_task(state) -> str:
    task_id = str(uuid.uuid4())
    with state.tasks_lock:
        state.tasks[task_id] = {
            "status": "queued",
            "submitted_at": time.time(),
            "progress": 0.0,
            "stage": "queued",
        }
    return task_id


def submit_task(
    state,
    filepath: str,
    lang: str,
    watermark_type: int,
    image_quality: int,
    burn_after_read: str,
    logo_preference: Optional[str],
    logger,
) -> str:
    task_id = create_task(state)
    _update_queue_metrics(state, task_id, logger)
    state.executor.submit(
        background_process,
        task_id,
        state,
        filepath,
        lang,
        watermark_type,
        image_quality,
        burn_after_read,
        logo_preference,
        logger,
    )
    return task_id


def background_process(
    task_id: str,
    state,
    filepath: str,
    lang: str,
    watermark_type: int,
    image_quality: int,
    burn_after_read: str,
    logo_preference: Optional[str],
    logger,
) -> None:
    start_time = time.time()
    try:
        with state.tasks_lock:
            state.tasks[task_id]["status"] = "processing"
            state.tasks[task_id]["progress"] = max(state.tasks[task_id].get("progress", 0), 0.01)
            state.tasks[task_id]["stage"] = "processing"

        def update_progress(progress, stage=None):
            with state.tasks_lock:
                task = state.tasks.get(task_id)
                if not task:
                    return
                current = task.get("progress", 0)
                task["progress"] = max(current, min(progress, 1))
                if stage:
                    task["stage"] = stage

        process_image(
            filepath,
            lang=lang,
            watermark_type=watermark_type,
            image_quality=image_quality,
            logo_preference=logo_preference,
            progress_callback=update_progress,
        )

        filename = os.path.basename(filepath)
        original_name, extension = os.path.splitext(filename)
        processed_filename = f"{original_name}_watermark{extension}"

        with state.tasks_lock:
            state.tasks[task_id]["status"] = "succeeded"
            state.tasks[task_id]["result"] = {
                "processed_image": f"/upload/{processed_filename}?lang={lang}&burn={burn_after_read}"
            }
            state.tasks[task_id]["progress"] = 1.0
            state.tasks[task_id]["stage"] = "done"

        with state.metrics_lock:
            state.metrics["succeeded_tasks"] += 1

    except WatermarkError as err:
        message_key = err.get_message_key()
        detail = err.get_detail()
        message = get_common_message(message_key, lang) or detail or get_common_message("unexpected_error", lang)
        if message_key == "unsupported_manufacturer" and detail:
            message = f"{message} ({detail})"

        with state.tasks_lock:
            state.tasks[task_id]["status"] = "failed"
            state.tasks[task_id]["error"] = message
            state.tasks[task_id]["progress"] = 1.0
            state.tasks[task_id]["stage"] = "failed"
        logger.warning("Task %s failed: %s", task_id, message)
        with state.metrics_lock:
            state.metrics["failed_tasks"] += 1

    except Exception:
        logger.exception("Unexpected error in background task %s", task_id)
        with state.tasks_lock:
            state.tasks[task_id]["status"] = "failed"
            state.tasks[task_id]["error"] = get_common_message("unexpected_error", lang)
            state.tasks[task_id]["progress"] = 1.0
            state.tasks[task_id]["stage"] = "failed"
        with state.metrics_lock:
            state.metrics["failed_tasks"] += 1

    finally:
        duration = time.time() - start_time
        with state.metrics_lock:
            total = state.metrics["total_tasks"]
            failed = state.metrics["failed_tasks"]
        failure_rate = (failed / total) if total else 0
        with state.tasks_lock:
            queue_length = sum(
                1 for info in state.tasks.values() if info.get("status") in {"queued", "processing"}
            )
        logger.info(
            "Task %s finished in %.2f s | queue=%s | failure_rate=%.2f%%",
            task_id,
            duration,
            queue_length,
            failure_rate * 100,
        )
