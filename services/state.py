from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import AppConfig


def _executor_factory(config: AppConfig) -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=config.executor_max_workers)


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
    executor: ThreadPoolExecutor = field(init=False)

    def __post_init__(self):
        """Initialize executor with default config."""
        from config.settings import AppConfig
        config = AppConfig()
        self.executor = _executor_factory(config)

    def set_executor_config(self, config: AppConfig) -> None:
        """Update executor with new configuration."""
        if self.executor:
            self.executor.shutdown(wait=False)
        self.executor = _executor_factory(config)
