from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
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

    def create_task(self, task_id: str, initial_data: dict) -> None:
        with self.tasks_lock:
            self.tasks[task_id] = initial_data

    def update_task(self, task_id: str, **fields: Any) -> None:
        with self.tasks_lock:
            task = self.tasks.get(task_id)
            if task is not None:
                task.update(fields)

    def get_task(self, task_id: str) -> Optional[dict]:
        with self.tasks_lock:
            task = self.tasks.get(task_id)
            return dict(task) if task is not None else None

    def count_tasks_by_status(self, *statuses: str) -> int:
        with self.tasks_lock:
            return sum(1 for info in self.tasks.values() if info.get("status") in statuses)

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait)
