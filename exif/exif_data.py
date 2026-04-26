"""EXIF 数据提取和格式化。"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
import piexif

from logging_utils import get_logger

logger = get_logger("autowatermark.exif_utils")


def _sanitize_make(value) -> str:
    sanitized = ''.join(ch for ch in str(value or "") if re.match(r'[a-zA-Z ]', ch))
    return ' '.join(sanitized.split())


def _sanitize_model(value) -> Optional[str]:
    sanitized = ''.join(ch for ch in str(value or "") if re.match(r'[a-zA-Z0-9\- ]', ch))
    sanitized = ' '.join(sanitized.split())
    return sanitized or None


def _format_decimal(value) -> Optional[str]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number.is_integer():
        return str(int(number))
    return str(round(number, 2)).rstrip("0").rstrip(".")


def _format_exiftool_date(value) -> str:
    date_taken = str(value or "Unknown Date")
    if ' ' in date_taken:
        index = date_taken.index(' ')
        substring = date_taken[:index]
        if ":" in substring:
            new_substring = substring.replace(':', '.')
            date_taken = date_taken[:index].replace(substring, new_substring) + date_taken[index:]

    if "T" in date_taken:
        date_taken = date_taken.replace("T", " ")
        index = date_taken.index(" ")
        substring = date_taken[:index]
        if ":" in substring:
            new_substring = substring.replace(':', '.')
            date_taken = date_taken[:index].replace(substring, new_substring) + date_taken[index:]
    return date_taken


def _find_exiftool():
    executable = shutil.which("exiftool")
    if executable:
        return executable

    project_root = Path(__file__).resolve().parents[1]
    local_exiftool = project_root / "3rdparty" / "exiftool" / "exiftool"
    if local_exiftool.exists():
        return str(local_exiftool)
    return None


def get_exif_data_with_exiftool(image_path: str) -> Optional[dict]:
    """Fallback metadata extraction for files that piexif cannot parse."""
    exiftool = _find_exiftool()
    if not exiftool:
        return None

    tags = [
        "-Make",
        "-Model",
        "-XiaomiModel",
        "-LensModel",
        "-Lens",
        "-LensType",
        "-FocalLengthIn35mmFormat",
        "-FocalLength",
        "-FNumber",
        "-ExposureTime",
        "-ISO",
        "-DateTimeOriginal",
    ]
    try:
        output = subprocess.check_output(
            [exiftool, "-j", "-n", *tags, image_path],
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        rows = json.loads(output.decode(errors="ignore"))
    except Exception as exc:
        logger.info("exiftool fallback failed for %s: %s", image_path, exc)
        return None

    if not rows:
        return None

    payload = rows[0]
    manufacturer = _sanitize_make(payload.get("Make"))
    camera_model = _sanitize_model(payload.get("Model"))
    xiaomi_model = _sanitize_model(payload.get("XiaomiModel"))
    if not manufacturer and xiaomi_model:
        manufacturer = "Xiaomi"
        camera_model = xiaomi_model
    elif not camera_model and xiaomi_model:
        camera_model = xiaomi_model
    if not manufacturer:
        return None

    lens_info = payload.get("LensModel") or payload.get("Lens") or payload.get("LensType") or "Unknown Lens"
    lens_info = round_floats_in_string(str(lens_info).replace("f", "\u0192"))

    focal_length = payload.get("FocalLengthIn35mmFormat") or payload.get("FocalLength")
    focal_length_text = _format_decimal(focal_length)
    f_number_text = _format_decimal(payload.get("FNumber"))
    iso_speed = payload.get("ISO") or 0
    date_taken = _format_exiftool_date(payload.get("DateTimeOriginal"))

    exposure_time = payload.get("ExposureTime")
    try:
        exposure_value = float(exposure_time)
    except (TypeError, ValueError):
        exposure_value = 0

    if focal_length_text and f_number_text and exposure_value:
        if exposure_value < 1:
            shutter = f"1/{int(round(1 / exposure_value))}s"
        else:
            shutter_value = int(exposure_value) if exposure_value.is_integer() else round(exposure_value, 2)
            shutter = f"{shutter_value}s"
        shooting_info = f"{focal_length_text}mm  \u0192/{f_number_text}  {shutter}  ISO{iso_speed}\n{date_taken}"
    else:
        shooting_info = "Invalid shooting info\n" + date_taken

    camera_info = f"{lens_info}\n{camera_model or ''}"
    if "xiaomi" in manufacturer.lower():
        camera_info = f"{manufacturer}\n{camera_model or ''}"

    return {
        "manufacturer": manufacturer,
        "camera_model": camera_model,
        "camera_info": camera_info,
        "shooting_info": shooting_info,
    }


def convert_to_int(value) -> float:
    if isinstance(value, tuple):
        if len(value) >= 2:
            numerator = value[0]
            denominator = value[1]
            if denominator:
                return numerator / denominator
            return 0
        return int(value[0]) if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Cannot convert string to int: '{value}'")
    raise ValueError("Unsupported type")


def _ensure_exif_dict(image_path: str, exif_dict: Optional[dict]) -> Optional[dict]:
    if exif_dict is not None:
        return exif_dict

    try:
        with Image.open(image_path) as image:
            exif_bytes = image.info.get('exif')
            if not exif_bytes:
                return None
            return piexif.load(exif_bytes)
    except Exception:
        return None


def get_manufacturer(image_path: str, exif_dict: Optional[dict] = None) -> Optional[str]:
    exif_dict = _ensure_exif_dict(image_path, exif_dict)
    if not exif_dict:
        return None

    try:
        manufacturer_bytes = exif_dict.get('0th', {}).get(piexif.ImageIFD.Make, b"")
        manufacturer = manufacturer_bytes.decode(errors='ignore').strip()
        sanitized = ''.join(ch for ch in manufacturer if re.match(r'[a-zA-Z ]', ch))
        return ' '.join(sanitized.split())
    except Exception:
        return None

def get_camera_model(exif_dict: Optional[dict]) -> Optional[str]:
    if not exif_dict:
        return None

    try:
        model_bytes = exif_dict.get('0th', {}).get(piexif.ImageIFD.Model, b"")
        if isinstance(model_bytes, (bytes, bytearray)):
            model = model_bytes.decode(errors='ignore')
        else:
            model = str(model_bytes)
        sanitized = ''.join(ch for ch in model if re.match(r'[a-zA-Z0-9\- ]', ch))
        sanitized = ' '.join(sanitized.split())
        return sanitized or None
    except Exception:
        return None


def get_exif_table(image_path: str, exif_dict: Optional[dict] = None) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[int]]:
    exif_dict = _ensure_exif_dict(image_path, exif_dict)
    if not exif_dict:
        return None, None, None, None

    try:
        exif_data = exif_dict.get('Exif', {})

        focal_length_35 = exif_data.get(piexif.ExifIFD.FocalLengthIn35mmFilm, (0, 1))
        # Some photos don't have focal length in 35mm film
        if focal_length_35 == (0, 1):
            focal_length = exif_data.get(piexif.ExifIFD.FocalLength, (0, 1))
            focal_length_35 = convert_to_int(focal_length)

        f_number = exif_data.get(piexif.ExifIFD.FNumber, (0, 1))
        exposure_time = exif_data.get(piexif.ExifIFD.ExposureTime, (0, 1))
        iso_speed = exif_data.get(piexif.ExifIFD.ISOSpeedRatings, 0)

        focal_length_value = focal_length_35
        f_number_value = f_number[0] / f_number[1] if f_number[1] != 0 else 0
        exposure_time_value = exposure_time[0] / exposure_time[1] if exposure_time[1] != 0 else 0

        f_number_value = round(f_number_value, 2) if f_number_value else 0

        return focal_length_value, f_number_value, exposure_time_value, iso_speed
    except KeyError as e:
        logger.debug("EXIF table missing key %s for %s", e, image_path)
        return None, None, None, None
    except Exception as e:
        logger.warning("Failed to read EXIF table from %s: %s", image_path, e)
        return None, None, None, None

def round_floats_in_string(s: str, decimal_places: int = 2) -> str:
    float_pattern = r'-?\d+\.\d+'
    def round_match(match):
        float_value = match.group(0)
        rounded_float = round(float(float_value), decimal_places)
        return str(rounded_float)

    result = re.sub(float_pattern, round_match, s)

    return result

def get_exif_data(image_path: str, exif_dict: Optional[dict] = None) -> Tuple[Optional[str], Optional[str]]:
    exif_dict = _ensure_exif_dict(image_path, exif_dict)
    if not exif_dict:
        return None, None

    try:
        exif_data = exif_dict.get('Exif', {})

        lens_raw = exif_data.get(piexif.ExifIFD.LensModel, b"Unknown Lens")
        lens_info = lens_raw.decode(errors='ignore') if isinstance(lens_raw, (bytes, bytearray)) else str(lens_raw)

        camera_make_raw = exif_dict.get('0th', {}).get(piexif.ImageIFD.Make, b"Unknown Make")
        camera_model_raw = exif_dict.get('0th', {}).get(piexif.ImageIFD.Model, b"Unknown Model")

        camera_make = camera_make_raw.decode(errors='ignore') if isinstance(camera_make_raw, (bytes, bytearray)) else str(camera_make_raw)
        camera_model_code = camera_model_raw.decode(errors='ignore') if isinstance(camera_model_raw, (bytes, bytearray)) else str(camera_model_raw)

        camera_make = ''.join(ch for ch in camera_make if re.match(r'[a-zA-Z ]', ch))
        camera_model_code = ''.join(ch for ch in camera_model_code if re.match(r'[a-zA-Z0-9\- ]', ch))

        focal_length_value, f_number_value, exposure_time_value, iso_speed = get_exif_table(image_path, exif_dict)

        datetime_raw = exif_data.get(piexif.ExifIFD.DateTimeOriginal, b"Unknown Date")
        date_taken = datetime_raw.decode(errors='ignore') if isinstance(datetime_raw, (bytes, bytearray)) else str(datetime_raw)
        camera_model = camera_model_code
        date_taken = _format_exiftool_date(date_taken)

        if str(lens_info) == "Unknown Lens":
            exif_ids = ["-LensModel", "-Lens", "-LensType"]
            lens_info = "Unknown Lens"
            exif_tool_path = Path("./3rdparty/exiftool/exiftool")
            if exif_tool_path.exists():
                for exif_id in exif_ids:
                    try:
                        output = subprocess.check_output(
                            [str(exif_tool_path), exif_id, image_path],
                            stderr=subprocess.STDOUT,
                        )
                    except Exception:
                        continue
                    output = output.decode(errors='ignore').strip().split(":")
                    if len(output) > 1:
                        lens_info = output[1].strip()
                        break

        if 'f' in str(lens_info):
            lens_info = str(lens_info).replace('f', '\u0192')  # \u0192 resembles the aperture symbol seen on iOS.

        if focal_length_value and f_number_value and exposure_time_value:
            if int(exposure_time_value) == exposure_time_value:
                exposure_time_value = int(exposure_time_value)
            if exposure_time_value < 1:
                shooting_info = f"{focal_length_value}mm  \u0192/{f_number_value}  1/{int(1 / exposure_time_value)}s  ISO{iso_speed}\n{date_taken}"
            else:
                shooting_info = f"{focal_length_value}mm  \u0192/{f_number_value} {exposure_time_value}s  ISO{iso_speed}\n{date_taken}"
        else:
            shooting_info = "Invalid shooting info\n" + date_taken

        lens_info = round_floats_in_string(lens_info)
        camera_info = f"{lens_info}\n{camera_model}"
        if "xiaomi" in camera_make.lower():
            camera_info = f"{camera_make}\n{camera_model}"

        return camera_info, shooting_info
    except KeyError as e:
        logger.debug("EXIF data missing key %s for %s", e, image_path)
        return None, None
    except Exception as e:
        logger.warning("Failed to read EXIF data from %s: %s", image_path, e)
        return None, None
