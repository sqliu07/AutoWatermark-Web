from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from services.i18n import get_error_message
from services.path_safety import resolve_under_root
from services.watermark_styles import is_style_enabled


class TaskStatus:
    QUEUED = "queued"
    NEEDS_LOGO = "needs_logo"
    NEEDS_OPTIONS = "needs_options"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStage:
    QUEUED = "queued"
    AWAITING_LOGO = "awaiting_logo"
    AWAITING_OPTIONS = "awaiting_options"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class LifecycleResult:
    payload: dict[str, Any]
    status_code: int


def create_waiting_logo_task(state, task_data: dict[str, Any]) -> str:
    from services.tasks import create_task

    return create_task(
        state,
        {
            **task_data,
            "status": TaskStatus.NEEDS_LOGO,
            "stage": TaskStage.AWAITING_LOGO,
            "progress": 0.0,
        },
    )


def create_waiting_options_task(state, task_data: dict[str, Any]) -> str:
    from services.tasks import create_task

    return create_task(
        state,
        {
            **task_data,
            "status": TaskStatus.NEEDS_OPTIONS,
            "stage": TaskStage.AWAITING_OPTIONS,
            "progress": 0.0,
        },
    )


def mark_waiting_options(state, task_id: str, **fields: Any) -> None:
    state.update_task(
        task_id,
        status=TaskStatus.NEEDS_OPTIONS,
        stage=TaskStage.AWAITING_OPTIONS,
        progress=0.0,
        **fields,
    )


def mark_processing(state, task_id: str, progress: float = 0.01) -> None:
    state.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        stage=TaskStage.PROCESSING,
        progress=progress,
    )


def mark_succeeded(state, task_id: str, result: dict[str, Any]) -> None:
    state.update_task(
        task_id,
        status=TaskStatus.SUCCEEDED,
        result=result,
        progress=1.0,
        stage=TaskStage.DONE,
    )


def mark_failed(state, task_id: str, error: str) -> None:
    state.update_task(
        task_id,
        status=TaskStatus.FAILED,
        error=error,
        progress=1.0,
        stage=TaskStage.FAILED,
    )


def task_payload_from_persisted_task(*, task_id: str, state, task: dict[str, Any], upload_folder: str, style_config, logger):
    from services.tasks import TaskPayload

    lang = task.get("lang", "zh")
    filepath = task.get("filepath")
    safe_filepath = resolve_under_root(upload_folder, filepath or "")
    if safe_filepath is None or not os.path.exists(safe_filepath):
        return None, LifecycleResult({"error": get_error_message("file_not_found", lang)}, 404)

    watermark_type = task.get("watermark_type")
    if not isinstance(watermark_type, int) or not is_style_enabled(style_config, watermark_type):
        return None, LifecycleResult({"error": get_error_message("unexpected_error", lang)}, 400)

    return TaskPayload(
        task_id=task_id,
        state=state,
        filepath=safe_filepath,
        lang=lang,
        watermark_type=watermark_type,
        image_quality=int(task.get("image_quality") or 85),
        burn_after_read=str(task.get("burn_after_read") or "0"),
        logo_preference=task.get("logo_preference"),
        style_config=style_config,
        logger=logger,
        preliminary_manufacturer=task.get("preliminary_manufacturer"),
        preserve_motion=True if task.get("preserve_motion") is None else bool(task.get("preserve_motion")),
        preserve_hdr=True if task.get("preserve_hdr") is None else bool(task.get("preserve_hdr")),
    ), None


def retry_failed_task(*, task_id: str, state, upload_folder: str, style_config, logger) -> LifecycleResult:
    from services.tasks import submit_existing_task

    task = state.get_task(task_id)
    if not task:
        return LifecycleResult({"status": "unknown"}, 404)
    if task.get("status") != TaskStatus.FAILED:
        return LifecycleResult({"error": "task is not failed"}, 409)

    payload, error = task_payload_from_persisted_task(
        task_id=task_id,
        state=state,
        task=task,
        upload_folder=upload_folder,
        style_config=style_config,
        logger=logger,
    )
    if error:
        return error

    state.update_task(
        task_id,
        status=TaskStatus.QUEUED,
        stage=TaskStage.QUEUED,
        progress=0.0,
        error=None,
        result=None,
    )
    submit_existing_task(task_id, payload)
    return LifecycleResult({"task_id": task_id}, 202)
