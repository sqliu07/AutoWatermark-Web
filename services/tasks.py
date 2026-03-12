import os
import time
import uuid
from typing import Optional, Set

from PIL import Image
import piexif

from constants import CommonConstants
from errors import WatermarkError
from exif_utils import get_manufacturer
from process import process_image
from services.i18n import get_common_message
from services.task_store import (
    count_tasks_by_status,
    get_task_stats,
    insert_task,
    update_task,
)


def allowed_file(filename: str, allowed_extensions: Set[str]) -> bool:
    """Check allowed file extensions."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


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


def _update_queue_metrics(db_path: str, task_id: str, logger) -> None:
    stats = get_task_stats(db_path)
    total = stats["total_tasks"]
    failed = stats["failed_tasks"]
    failure_rate = (failed / total) if total else 0
    queue_length = count_tasks_by_status(db_path, "queued")
    logger.info(
        "Queued task %s | queue=%s | failure_rate=%.2f%%",
        task_id,
        queue_length,
        failure_rate * 100,
    )


def create_task(
    db_path: str,
    *,
    filepath: str,
    lang: str,
    watermark_type: int,
    image_quality: int,
    burn_after_read: bool,
    logo_preference: Optional[str],
) -> str:
    task_id = str(uuid.uuid4())
    insert_task(
        db_path,
        task_id=task_id,
        lang=lang,
        watermark_type=watermark_type,
        image_quality=image_quality,
        burn_after_read=burn_after_read,
        logo_preference=logo_preference,
        input_path=filepath,
        submitted_at=time.time(),
    )
    return task_id


def submit_task(
    state,
    db_path: str,
    filepath: str,
    lang: str,
    watermark_type: int,
    image_quality: int,
    burn_after_read: str,
    logo_preference: Optional[str],
    style_config,
    logger,
) -> str:
    burn_after_read_bool = str(burn_after_read).strip() == "1"
    task_id = create_task(
        db_path,
        filepath=filepath,
        lang=lang,
        watermark_type=watermark_type,
        image_quality=image_quality,
        burn_after_read=burn_after_read_bool,
        logo_preference=logo_preference,
    )
    _update_queue_metrics(db_path, task_id, logger)
    state.executor.submit(
        background_process,
        task_id,
        db_path,
        filepath,
        lang,
        watermark_type,
        image_quality,
        burn_after_read,
        logo_preference,
        style_config,
        logger,
    )
    return task_id


def background_process(
    task_id: str,
    db_path: str,
    filepath: str,
    lang: str,
    watermark_type: int,
    image_quality: int,
    burn_after_read: str,
    logo_preference: Optional[str],
    style_config,
    logger,
) -> None:
    start_time = time.time()
    try:
        update_task(
            db_path,
            task_id,
            status="processing",
            stage="processing",
            started_at=start_time,
            progress=0.01,
        )

        def update_progress(progress, stage=None):
            fields = {"progress": max(0.01, min(progress, 1.0))}
            if stage:
                fields["stage"] = stage
            update_task(db_path, task_id, **fields)

        process_image(
            filepath,
            lang=lang,
            watermark_type=watermark_type,
            image_quality=image_quality,
            logo_preference=logo_preference,
            progress_callback=update_progress,
            style_config=style_config,
        )

        filename = os.path.basename(filepath)
        original_name, extension = os.path.splitext(filename)
        processed_filename = f"{original_name}_watermark{extension}"
        result_url = f"/upload/{processed_filename}?lang={lang}&burn={burn_after_read}"
        output_path = os.path.join(os.path.dirname(filepath), processed_filename)

        update_task(
            db_path,
            task_id,
            status="succeeded",
            result_url=result_url,
            output_path=output_path,
            progress=1.0,
            stage="done",
            finished_at=time.time(),
            error=None,
        )

    except WatermarkError as err:
        message_key = err.get_message_key()
        detail = err.get_detail()
        message = get_common_message(message_key, lang) or detail or get_common_message("unexpected_error", lang)
        if message_key == "unsupported_manufacturer" and detail:
            message = f"{message} ({detail})"
        elif message_key == "unexpected_error" and detail:
            message = detail

        update_task(
            db_path,
            task_id,
            status="failed",
            error=message,
            progress=1.0,
            stage="failed",
            finished_at=time.time(),
        )
        if message_key == "unexpected_error":
            logger.exception(
                "Task %s failed: %s | detail=%s | file=%s | style=%s",
                task_id,
                message,
                detail or "-",
                filepath,
                watermark_type,
            )
        else:
            logger.warning(
                "Task %s failed: %s | detail=%s | file=%s | style=%s",
                task_id,
                message,
                detail or "-",
                filepath,
                watermark_type,
            )

    except Exception:
        logger.exception("Unexpected error in background task %s", task_id)
        update_task(
            db_path,
            task_id,
            status="failed",
            error=get_common_message("unexpected_error", lang),
            progress=1.0,
            stage="failed",
            finished_at=time.time(),
        )

    finally:
        duration = time.time() - start_time
        stats = get_task_stats(db_path)
        total = stats["total_tasks"]
        failed = stats["failed_tasks"]
        failure_rate = (failed / total) if total else 0
        queue_length = count_tasks_by_status(db_path, "queued", "processing")
        logger.info(
            "Task %s finished in %.2f s | queue=%s | failure_rate=%.2f%%",
            task_id,
            duration,
            queue_length,
            failure_rate * 100,
        )
