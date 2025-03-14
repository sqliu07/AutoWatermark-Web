from PIL import Image
import piexif
import subprocess
import os
import re

def convert_to_int(value):
    if isinstance(value, tuple):
        return int(value[0])
    elif isinstance(value, int):
        return value
    elif isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Cannot convert string to int: '{value}'")
    else:
        raise ValueError("Unsupported type")
    
def get_manufacturer(image_path):
    try:
        image = Image.open(image_path)
        exif_dict = piexif.load(image.info['exif'])
        manufacturer = exif_dict['0th'].get(piexif.ImageIFD.Make, b"").decode().strip()
        for letter in manufacturer:
            if re.match(r'[a-zA-Z]', letter):
                continue
            else:
                manufacturer = manufacturer.replace(letter, '')
        return manufacturer
    except KeyError:
        return None
    except Exception as e:
        return None

def find_logo(manufacturer):
    logo_dir = "./logos"
    for root, dirs, files in os.walk(logo_dir):
        for file in files:
            if file.lower().startswith(manufacturer.lower().split()[0]) or manufacturer.lower().startswith(file.lower().split('.')[0]):
                return os.path.join(root, file)
    return None

def get_exif_table(image_path):
    try:
        image = Image.open(image_path)
        exif_dict = piexif.load(image.info['exif'])
        exif_data = exif_dict['Exif']

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

        return focal_length_value, f_number_value, exposure_time_value, iso_speed
    except KeyError:
        return None, None, None, None
    except Exception as e:
        return None, None, None, None

def get_exif_data(image_path):
    try:
        image = Image.open(image_path)
        exif_dict = piexif.load(image.info['exif'])
        exif_data = exif_dict['Exif']

        lens_info = exif_data.get(piexif.ExifIFD.LensModel, b"Unknown Lens").decode()
        camera_make = exif_dict['0th'].get(piexif.ImageIFD.Make, b"Unknown Make").decode()
        camera_model_code = exif_dict['0th'].get(piexif.ImageIFD.Model, b"Unknown Model").decode()

        for letter in camera_make:
            if re.match(r'[a-zA-Z]', letter):
                continue
            else:
                camera_make = camera_make.replace(letter, '')

        for letter in camera_model_code:
            if re.match(r'[a-zA-Z0-9\- ]', letter):
                continue
            else:
                camera_model_code = camera_model_code.replace(letter, '')
    
        focal_length_value, f_number_value, exposure_time_value, iso_speed = get_exif_table(image_path)
        
        datetime = exif_data.get(piexif.ExifIFD.DateTimeOriginal, b"Unknown Date").decode()
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
            exif_tool_path = "./3rdparty/exiftool/exiftool"
            for exif_id in exif_ids:
                output = subprocess.check_output([exif_tool_path, exif_id, image_path])
                output = output.decode().strip().split(":")
                if len(output) > 1:
                    lens_info = output[1].strip()
                    break

        if 'f'in str(lens_info):
            lens_info = lens_info.replace('f', '\u0192') #\u0192 means another type of "f" for the Aperture value, looks like that on iPhone.

        # Format shooting_info only if values are valid
        if focal_length_value and f_number_value and exposure_time_value:
            if int(exposure_time_value) == exposure_time_value:
                exposure_time_value = int(exposure_time_value)
            if exposure_time_value < 1:
                shooting_info = f"{focal_length_value}mm  \u0192/{f_number_value}  1/{int(1 / exposure_time_value)}s  ISO{iso_speed}\n{datetime}"
            else:
                shooting_info = f"{focal_length_value}mm  \u0192/{f_number_value} {exposure_time_value}s  ISO{iso_speed}\n{datetime}"
        else:
            shooting_info = "Invalid shooting info\n" + datetime

        camera_info = f"{lens_info}\n{camera_model}"

        return camera_info, shooting_info
    except KeyError:
        return None, None
    except Exception as e:
        return None, None

