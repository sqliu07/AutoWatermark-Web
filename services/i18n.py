import json
from typing import Dict, Optional

from config.settings import AppConfig


def load_translations(path: str, logger=None) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if logger:
            logger.error("Translation file not found!")
        return {}


def normalize_lang(lang: Optional[str]) -> str:
    if not lang:
        return "zh"
    return lang.split("?")[0]


def get_message(key: str, lang: str = "zh", config: Optional[AppConfig] = None) -> Optional[str]:
    if config is None:
        config = AppConfig()
    return config.get_error_message(key, lang, category="app")


def get_common_message(key: str, lang: str = "zh", config: Optional[AppConfig] = None) -> Optional[str]:
    if config is None:
        config = AppConfig()
    return config.get_error_message(key, lang, category="common")
