from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from constants import AppConstants


def _executor_factory() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=AppConstants.EXECUTOR_MAX_WORKERS)


def _metrics_factory() -> dict:
    return {
        "total_tasks": 0,
        "succeeded_tasks": 0,
        "failed_tasks": 0,
    }


@dataclass
class AppState:
    burn_queue: dict = field(default_factory=dict)
    burn_queue_lock: Lock = field(default_factory=Lock)
    metrics_lock: Lock = field(default_factory=Lock)
    tasks_lock: Lock = field(default_factory=Lock)
    metrics: dict = field(default_factory=_metrics_factory)
    tasks: dict = field(default_factory=dict)
    executor: ThreadPoolExecutor = field(default_factory=_executor_factory)
