import json
from typing import Dict, Optional

from constants import CommonConstants


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


def get_error_message(key: str, lang: str = "zh") -> Optional[str]:
    """统一的错误消息查找函数，从 CommonConstants.ERROR_MESSAGES 获取。"""
    return CommonConstants.ERROR_MESSAGES.get(key, {}).get(lang)


# 兼容别名，后续清理
get_message = get_error_message
get_common_message = get_error_message
