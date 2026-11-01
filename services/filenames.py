"""Safe, human-readable download names independent from storage paths."""

import os
import unicodedata


def download_name(original: str | None, stored: str) -> str:
    if not original:
        return os.path.basename(stored)
    name = unicodedata.normalize("NFC", original.replace("\\", "/").rsplit("/", 1)[-1])
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C")).strip(" .")
    stem = os.path.splitext(name)[0].strip(" .")
    stem = stem.encode("utf-8")[:180].decode("utf-8", errors="ignore")
    if not stem:
        return os.path.basename(stored)
    return stem + "_watermark" + os.path.splitext(stored)[1]


def unique_archive_name(name: str, used: set[str]) -> str:
    stem, extension = os.path.splitext(name)
    candidate = name
    number = 2
    while candidate.casefold() in used:
        candidate = f"{stem} ({number}){extension}"
        number += 1
    used.add(candidate.casefold())
    return candidate
