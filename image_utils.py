from constants import ImageConstants
from PIL import Image, ImageDraw, ImageFont, ImageOps

def is_landscape(image):
    return image.width >= image.height

def reset_image_orientation(image):
    try:
        exif = image._getexif()
        if exif:
            orientation = exif.get(274)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except Exception as e:
        print(f"Error resetting orientation: {e}")
    return image

def image_resize(image,ratio):
    return image.resize((int(image.width*ratio / 2),int(image.height*ratio / 2)),Image.LANCZOS)

def text_to_image(text, font_path, font_size, color='black'):
    font = ImageFont.truetype(font_path, font_size)
    _, _, text_width, text_height = font.getbbox(text)
    image = Image.new("RGB", (text_width, text_height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), text, font=font, fill=color)
    return image

def resize_logo(logo, height):
    ori_logo_width, ori_logo_height = logo.size
    resize_factor = height / ori_logo_height
    return logo.resize(
        (int(ori_logo_width * resize_factor), int(ori_logo_height * resize_factor)), Image.LANCZOS
    )

def paste_text_logo(img, positions):
    for text_img, pos in positions:
        img.paste(text_img, pos)

def draw_line(origin_image, start_x, start_y, end_x, end_y, line_width):
    draw = ImageDraw.Draw(origin_image)
    draw.line((start_x, start_y, end_x, end_y), fill=(128, 128, 128), width=line_width)

def calculate_position(x, y_offset, x_adjust=0, y_adjust=0):
        return (x + x_adjust, y_offset + y_adjust)

def generate_watermark_image(origin_image, logo_path, camera_info, shooting_info,
                             font_path_thin, font_path_bold, watermark_type=3,
                             font_size=60, return_metadata=False):
    ori_width, ori_height = origin_image.size
    bottom_width = int(ImageConstants.ORIGIN_BOTTOM_BORDER_RATIO * ori_height)
    top_width = int(ImageConstants.ORIGIN_TOP_BORDER_RATIO * ori_height)
    border_width = top_width

    border_left = 0
    border_top = 0
    border_right = 0
    border_bottom = 0
        
    if watermark_type == 1:
        border_left = border_right = border_width
        border_top = top_width
        border_bottom = bottom_width
        origin_image = ImageOps.expand(origin_image, 
                        border=(border_width, top_width, border_width, bottom_width), 
                        fill='white')
    elif watermark_type == 2:
        top_width = 0
        border_left = border_right = 0
        border_top = 0
        border_bottom = bottom_width
        origin_image = ImageOps.expand(origin_image, 
                        border=(0, 0, 0, bottom_width), 
                        fill='white')
    else:
        border_left = border_right = border_width
        border_top = top_width
        border_bottom = int(1.5 * bottom_width)
        origin_image = ImageOps.expand(origin_image, 
                        border=(border_width, top_width, border_width, border_bottom), 
                        fill='white')
    expanded_width, expanded_height = origin_image.size
    line_blank_ratio = 0.017
    line_width = 1 if max(expanded_width, expanded_height) < 3000 else 2
    ar_ratio = max(expanded_width, expanded_height) / min(expanded_width, expanded_height)
    line_blank = int(line_blank_ratio * min(expanded_width, expanded_height))
    logo_ratio = ImageConstants.LOGO_RATIO
    logo_location_denominator = 4
    text_resize_factor = bottom_width * 1.5 / ImageConstants.ORIGIN_BOTTOM_HEIGHT

    if (is_landscape(origin_image)):
        font_size = 120
        line_blank = int(line_blank / ar_ratio)
        logo_ratio = 0.085
        bottom_width = bottom_width * 4
        text_resize_factor = text_resize_factor / 1.5
        
    if (watermark_type == 3):
        logo_ratio = 0.095

    left_top = image_resize(text_to_image(camera_info[0], font_path_bold, font_size), text_resize_factor)
    left_bottom = image_resize(text_to_image(camera_info[1], font_path_thin, font_size), text_resize_factor)
    right_top = image_resize(text_to_image(shooting_info[0], font_path_bold, font_size), text_resize_factor)
    right_bottom = image_resize(text_to_image(shooting_info[1], font_path_thin, font_size), text_resize_factor)


    logo = Image.open(logo_path).convert("RGBA")
    logo_height = int(ori_height * logo_ratio)
    ori_logo_width, ori_logo_height = logo.size
    
    logo_resize_factor = 0.5 * logo_height / ori_logo_height
    logo = logo.resize((int(ori_logo_width * logo_resize_factor),
                        int(ori_logo_height * logo_resize_factor)),
                        Image.LANCZOS)

    text_image_height = left_top.height
    right_top_width = right_top.width
    
    row_1 = logo
    row2 = right_top

    text_block_height = top_width + ori_height + int(bottom_width / 2) - int(5 * text_image_height / 4)
    line_start_y_landscape = top_width + ori_height + int(bottom_width / 2) - int(19 * text_image_height / 3)
    line_end_y_landscape = top_width + ori_height + int(bottom_width / 2) - int(14 * text_image_height / 3)

    line_start_y_portrait = top_width + ori_height + int(bottom_width / 2) - int(1.8 * text_image_height / 2)
    line_end_y_portrait = top_width + ori_height + int(bottom_width / 2) + int(2.3 * text_image_height / 2)

    def get_positions(orientation, watermark_type):
        x_left = border_width
        x_right = border_width + ori_width - right_top_width if watermark_type == 1 else ori_width - right_top_width - border_width 
        y_base = top_width + ori_height + int(bottom_width / 2)

        positions = [
            (left_top, calculate_position(x_left, y_base, y_adjust=-int(20 * text_image_height / 3))),
            (left_bottom, calculate_position(x_left, y_base, y_adjust=-int(16.5 * text_image_height / 3))),
            (right_top, calculate_position(x_right, y_base, y_adjust=-int(20 * text_image_height / 3))),
            (right_bottom, calculate_position(x_right, y_base, y_adjust=-int(16.5 * text_image_height / 3))),
            (logo, calculate_position(x_right - logo.width - 2 * line_blank, y_base, y_adjust=-int(9 * text_image_height / 2) - logo.height))
        ]

        if orientation == "portrait":
            positions = [
                (left_top, calculate_position(x_left, y_base, y_adjust=-int(9 * text_image_height / 8))),
                (left_bottom, calculate_position(x_left, y_base, y_adjust=int(1 * text_image_height / 8))),
                (right_top, calculate_position(x_right, y_base, y_adjust=-int(9 * text_image_height / 8))),
                (right_bottom, calculate_position(x_right, y_base, y_adjust=int(1 * text_image_height / 8))),
                (logo, calculate_position(x_right - logo.width - 2 * line_blank, text_block_height, y_adjust=int(text_image_height / logo_location_denominator)))
            ]
            
        if watermark_type == 3:
            if orientation == "landscape":
                positions = [
                    (row_1, calculate_position(int((expanded_width - logo.width / 2) / 2), 
                                              y_base, 
                                              y_adjust=-int(20 * text_image_height / 3))),
                     (row2, calculate_position(int((expanded_width - row2.width) / 2), 
                                              y_base, 
                                              y_adjust=-int(12.5 * text_image_height / 3))),
            ]
            else:
                positions = [
                    (row_1, calculate_position(int((expanded_width - logo.width) / 2), 
                                              y_base, 
                                              y_adjust=-int(9 * text_image_height / 8))),
                    (row2, calculate_position(int((expanded_width - row2.width) / 2), 
                                              y_base, 
                                              y_adjust=int(19 * text_image_height / 8))),
            ]
        return positions

    def get_line_coordinates(orientation, watermark_type):
        x = ori_width - right_top_width - line_blank + (border_width if watermark_type == 1 else - border_width)
        if orientation == "landscape":
            return x, line_start_y_landscape, x, line_end_y_landscape
        return x, line_start_y_portrait, x, line_end_y_portrait

    orientation = "landscape" if is_landscape(origin_image) else "portrait"
    positions = get_positions(orientation, watermark_type)
    line_coords = get_line_coordinates(orientation, watermark_type)

    paste_text_logo(origin_image, positions)
    if watermark_type != 3:
        draw_line(origin_image, *line_coords, line_width)

    # Ensure even dimensions for downstream video processing (YUV420 requirement)
    pad_right = 1 if origin_image.width % 2 else 0
    pad_bottom = 1 if origin_image.height % 2 else 0
    if pad_right or pad_bottom:
        origin_image = ImageOps.expand(origin_image, border=(0, 0, pad_right, pad_bottom), fill='white')

    if return_metadata:
        content_box = (
            border_left,
            border_top,
            border_left + ori_width,
            border_top + ori_height,
        )
        overlay_image = origin_image.copy().convert("RGBA")
        transparent_region = Image.new("RGBA", (ori_width, ori_height), (0, 0, 0, 0))
        overlay_image.paste(transparent_region, content_box)
        metadata = {
            "overlay_image": overlay_image,
            "content_box": content_box,
            "final_size": origin_image.size,
        }
        return origin_image, metadata

    return origin_image
