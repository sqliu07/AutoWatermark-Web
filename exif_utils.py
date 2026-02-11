from constants import CommonConstants
from PIL import Image
import piexif
import subprocess
import re
from pathlib import Path

from logging_utils import get_logger


LOGO_DIR = Path("./logos")
logger = get_logger("autowatermark.exif_utils")


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

def convert_to_int(value):
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


def _ensure_exif_dict(image_path, exif_dict):
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


def get_manufacturer(image_path, exif_dict=None):
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

def get_camera_model(exif_dict):
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


def find_logo(manufacturer):
    if not manufacturer:
        return None

    normalized = _normalize_brand(manufacturer)
    candidates = []
    if normalized:
        candidates.append(normalized)

    from config.settings import AppConfig
    config = AppConfig()
    alias = config.normalize_brand(normalized)
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


def get_exif_table(image_path, exif_dict=None):
    exif_dict = _ensure_exif_dict(image_path, exif_dict)
    if not exif_dict:
        return None, None, None, None

    try:
        exif_data = exif_dict.get('Exif', {})

        focal_length_35 = exif_data.get(piexif.ExifIFD.FocalLengthIn35mmFilm, (0, 1))
        #Some photos don't have focal length in 35mm film
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
    except KeyError:
        return None, None, None, None
    except Exception as e:
        return None, None, None, None

def round_floats_in_string(s, decimal_places=2):
    float_pattern = r'-?\d+\.\d+'
    def round_match(match):
        float_value = match.group(0)
        rounded_float = round(float(float_value), decimal_places)
        return str(rounded_float)

    result = re.sub(float_pattern, round_match, s)

    return result
def get_exif_data(image_path, exif_dict=None):
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
        datetime = datetime_raw.decode(errors='ignore') if isinstance(datetime_raw, (bytes, bytearray)) else str(datetime_raw)
        camera_model = camera_model_code

        if ' ' in datetime:
            index = datetime.index(' ')
            substring = datetime[:index]
            if ":" in substring:
                new_substring = substring.replace(':', '.')
                datetime = datetime[:index].replace(substring, new_substring) + datetime[index:]

        if "T" in datetime:
            datetime = datetime.replace("T", " ")
            index = datetime.index(" ")
            substring = datetime[:index]
            if ":" in substring:
                new_substring = substring.replace(':', '.')
                datetime = datetime[:index].replace(substring, new_substring) + datetime[index:]

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
                shooting_info = f"{focal_length_value}mm  \u0192/{f_number_value}  1/{int(1 / exposure_time_value)}s  ISO{iso_speed}\n{datetime}"
            else:
                shooting_info = f"{focal_length_value}mm  \u0192/{f_number_value} {exposure_time_value}s  ISO{iso_speed}\n{datetime}"
        else:
            shooting_info = "Invalid shooting info\n" + datetime

        round_floats_in_string(lens_info)
        camera_info = f"{lens_info}\n{camera_model}"
        if "xiaomi" in camera_make.lower():
            camera_info = f"{camera_make}\n{camera_model}"

        return camera_info, shooting_info
    except KeyError:
        return None, None
    except Exception as e:
        return None, None
