from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from constants import AppConstants


def _executor_factory() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=AppConstants.EXECUTOR_MAX_WORKERS)

@dataclass
class AppState:
    executor: ThreadPoolExecutor = field(default_factory=_executor_factory)
