import json
import threading
from typing import Optional

from constants import CommonConstants
from logging_utils import get_logger

logger = get_logger("autowatermark.i18n")

_error_messages: dict = {}
_load_lock = threading.Lock()


def _ensure_loaded() -> None:
    global _error_messages
    if _error_messages:
        return
    with _load_lock:
        if _error_messages:
            return
        try:
            with open(CommonConstants.ERROR_MESSAGES_PATH, "r", encoding="utf-8") as f:
                _error_messages = json.load(f)
        except FileNotFoundError:
            logger.error("Error messages file not found: %s", CommonConstants.ERROR_MESSAGES_PATH)
            _error_messages = {}


def normalize_lang(lang: Optional[str]) -> str:
    if not lang:
        return "zh"
    candidate = lang.split("?")[0].strip().lower()
    if candidate in {"zh", "en"}:
        return candidate
    return "zh"


def get_error_message(key: str, lang: str = "zh", **kwargs) -> Optional[str]:
    _ensure_loaded()
    msg = _error_messages.get(key, {}).get(lang)
    if msg and kwargs:
        return msg.format(**kwargs)
    return msg
