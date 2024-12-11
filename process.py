from exif_utils import *
from image_utils import *

from PIL import Image
import sys

EDGE_WIDTH = 120
EDGE_RATIO = 0.12
EDGE_WIDTH_RATIO = 0.03
FONT_SIZE = 100

GLOBAL_FONT_PATH_BOLD = "./fonts/AlibabaPuHuiTi-2-85-Bold.otf"
GLOBAL_FONT_PATH_LIGHT = "./fonts/AlibabaPuHuiTi-2-45-Light.otf"

def add_borders_logo_and_text(image_path, notify = False,preview = False):
    try:
        original_name, extension = os.path.splitext(image_path)
        output_path = f"{original_name}_watermark{extension}"
        # Todo: Add more selections
        manufacturer = get_manufacturer(image_path)
        if manufacturer is not None:
            logo_path = find_logo(manufacturer)
            print(f"Found logo for manufacturer: {logo_path}")
            if logo_path is None:
                raise ValueError("Unspported manufacturer! Please wait for our update.")
        else:
            raise ValueError("This image does not contain valid exif data!")
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

        new_image = generate_watermark_image(image, logo_path, camera_info_lines, shooting_info_lines, GLOBAL_FONT_PATH_LIGHT, GLOBAL_FONT_PATH_BOLD)

        if preview:
            return new_image
        else:
            new_image.save(output_path, exif=exif_bytes, quality=90)  # keep exif data
            print("sending to server\n")
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
    if len(sys.argv) < 2:
        print("No file path provided!")
        sys.exit(1)

    image_path = sys.argv[1]
    
    notify = False
    result = add_borders_logo_and_text(image_path, notify)
    print(f"Processed image saved to {result}") 
