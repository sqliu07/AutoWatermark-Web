"""品牌识别与 logo 查找。"""

import re
from pathlib import Path

from constants import CommonConstants

LOGO_DIR = Path("./logos")


def _normalize_brand(value):
    cleaned = re.sub(r"[^a-z0-9]", "", value.lower())
    return cleaned


def _build_logo_index():
    index = {}
    if not LOGO_DIR.exists():
        return index

    for file_path in LOGO_DIR.rglob("*"):
        if file_path.is_file():
            stem = _normalize_brand(file_path.stem)
            if stem and stem not in index:
                index[stem] = str(file_path)
    return index


_LOGO_INDEX = _build_logo_index()


def find_logo(manufacturer):
    if not manufacturer:
        return None

    normalized = _normalize_brand(manufacturer)
    candidates = []
    if normalized:
        candidates.append(normalized)

    alias = CommonConstants.BRAND_ALIASES.get(normalized)
    if alias:
        alias_normalized = _normalize_brand(alias)
        if alias_normalized:
            candidates.append(alias_normalized)

    for token in manufacturer.split():
        token_normalized = _normalize_brand(token)
        if token_normalized and token_normalized not in candidates:
            candidates.append(token_normalized)

    for candidate in candidates:
        if candidate in _LOGO_INDEX:
            return _LOGO_INDEX[candidate]

    return None
