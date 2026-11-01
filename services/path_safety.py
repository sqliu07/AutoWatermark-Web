from __future__ import annotations

import os


def resolve_under_root(root: str, *parts: str) -> str | None:
    root_path = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_path, *parts))
    try:
        if os.path.commonpath([root_path, candidate]) != root_path:
            return None
    except ValueError:
        return None
    return candidate


def protected_state_paths(db_path: str | None) -> set[str]:
    if not db_path:
        return set()
    database = os.path.realpath(db_path)
    return {database + suffix for suffix in ("", "-wal", "-shm", "-journal", ".lock")}
