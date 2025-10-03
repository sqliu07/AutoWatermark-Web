import logging
import os
from typing import Optional


_LOG_DIR = "logs"
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")


def _ensure_log_dir() -> str:
    os.makedirs(_LOG_DIR, exist_ok=True)
    return os.path.abspath(_LOG_FILE)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger configured to write both to stdout and the shared log file."""
    logfile_path = _ensure_log_dir()
    logger_name = name or "autowatermark"
    logger = logging.getLogger(logger_name)

    # Avoid attaching duplicate handlers when called multiple times.
    def _has_file_handler() -> bool:
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == logfile_path:
                return True
        return False

    if not _has_file_handler():
        file_handler = logging.FileHandler(logfile_path)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(file_handler)

    if not any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(stream_handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger

