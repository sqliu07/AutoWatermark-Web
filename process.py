from exif_utils import *
from image_utils import *
from constants import CommonConstants

from PIL import Image
import sys

def get_message(key, lang='zh'):
    return CommonConstants.ERROR_MESSAGES.get(key, {}).get(lang)

def add_borders_logo_and_text(image_path, lang = 'zh', watermark_type = 1, image_quailty = 95, notify = False, preview = False):
    try:
        original_name, extension = os.path.splitext(image_path)
        output_path = f"{original_name}_watermark{extension}"
        # Todo: Add more selections
        manufacturer = get_manufacturer(image_path)
        if manufacturer is not None and len(manufacturer) > 0:
            logo_path = find_logo(manufacturer)
            if logo_path is None:
                raise ValueError(get_message("unsupported_manufacturer", lang))
        else:
            raise ValueError(get_message("no_exif_data", lang))
        image = Image.open(image_path)
        image = reset_image_orientation(image)  # Reset orientation
        exif_dict = None
        exif_bytes = None

        try:
            exif_dict = piexif.load(image.info.get('exif', b''))
            exif_bytes = piexif.dump(exif_dict)
        except Exception:
            return None

        result = get_exif_data(image_path)

        if result is not None:
            camera_info, shooting_info = result

        camera_info_lines, shooting_info_lines = camera_info.split('\n'), shooting_info.split('\n')

        new_image = generate_watermark_image(image, logo_path, camera_info_lines, shooting_info_lines, 
                                             CommonConstants.GLOBAL_FONT_PATH_LIGHT, CommonConstants.GLOBAL_FONT_PATH_BOLD, watermark_type)

        if preview:
            return new_image
        else:
            print(image_quailty)
            new_image.save(output_path, exif=exif_bytes, quality=image_quailty)  # keep exif data
            if notify:
                url = "8.152.219.197:9010/watermark"
                title = "This is your image with watermark."
                priority = "high"
                command = f'curl -H "Title: {title}" -H"Priority: {priority}" -T {output_path} {url}'
                os.system(command)
            return True
    except Exception as e:
         print(f"{str(e)}", file=sys.stderr)
         sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Invalid arguments!")
        sys.exit(1)

    image_path = sys.argv[1]
    lang = sys.argv[2]
    watermark_type = sys.argv[3]
    image_quality = sys.argv[4]
 
    notify = False
    result = add_borders_logo_and_text(image_path, lang, int(watermark_type), int(image_quality), notify)