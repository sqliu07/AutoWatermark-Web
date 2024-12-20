from PIL import Image, ImageDraw, ImageFont, ImageOps

ORIGIN_BOTTOM_BORDER_RATIO = 0.08
ORIGIN_TOP_BORDER_RATIO = 0.03
LOGO_RATIO = 0.07
ORIGIN_BOTTOM_HEIGHT = 250

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

def generate_watermark_image(origin_image, logo_path, camera_info, shooting_info, font_path_thin, font_path_bold, font_size = 60):
    # origin_image = Image.open(origin_image_path).convert("RGB")
    line_blank = 40
    ori_width, ori_height = origin_image.size
    bottom_width = int(ORIGIN_BOTTOM_BORDER_RATIO * ori_height)
    top_width = int(ORIGIN_TOP_BORDER_RATIO * ori_height)
    border_width = top_width
    origin_image = ImageOps.expand(origin_image, 
                    border=(border_width, top_width, border_width, bottom_width), 
                    fill='white')
       
    logo_ratio = LOGO_RATIO
    
    logo_location_denominator = 4
    
    text_resize_factor = bottom_width * 1.5 / ORIGIN_BOTTOM_HEIGHT
 
    if (is_landscape(origin_image)):
        font_size = 120
        line_blank = 70
        logo_ratio = 0.085
        logo_location_denominator = 0.6
        bottom_width = bottom_width * 4
        text_resize_factor = text_resize_factor / 1.5
    left_top = text_to_image(camera_info[0], font_path_bold, font_size)
    left_bottom = text_to_image(camera_info[1], font_path_thin, font_size)
    right_top = text_to_image(shooting_info[0], font_path_bold, font_size)
    right_bottom = text_to_image(shooting_info[1], font_path_thin, font_size)
    
    logo_height = int(ori_height * logo_ratio)
    logo = Image.open(logo_path).convert("RGBA")
    ori_logo_width, ori_logo_height = logo.size
    
    logo_resize_factor = logo_height / ori_logo_height
    logo = logo.resize((int(ori_logo_width * logo_resize_factor / 2), 
                        int(ori_logo_height * logo_resize_factor / 2)), 
                        Image.LANCZOS)
    
    left_top = image_resize(left_top, text_resize_factor)
    left_bottom = image_resize(left_bottom, text_resize_factor)
    right_top = image_resize(right_top, text_resize_factor)
    right_bottom = image_resize(right_bottom, text_resize_factor)   
    
    text_iamge_height = left_top.height
    right_top_width = right_top.width  
    
    if (is_landscape(origin_image)):
        text_block_height = top_width + ori_height + int(bottom_width / 2) - int(5 * text_iamge_height / 4)

        origin_image.paste(left_top, 
                           (border_width, 
                            top_width + ori_height + int(bottom_width / 2) - int(20 * text_iamge_height / 3))), 
        origin_image.paste(left_bottom, 
                           (border_width, 
                            top_width + ori_height + int(bottom_width / 2) - int(16.5 * text_iamge_height / 3)))
        origin_image.paste(right_top, 
                           (border_width + ori_width - right_top_width, 
                            top_width + ori_height + int(bottom_width / 2) - int(20 * text_iamge_height / 3)))
        origin_image.paste(right_bottom, 
                           (border_width + ori_width - right_top_width, 
                            top_width + ori_height + int(bottom_width / 2) - int(16.5 * text_iamge_height / 3)))    

        draw = ImageDraw.Draw(origin_image)

        draw.line((border_width + ori_width - right_top_width - line_blank,
                   top_width + ori_height + int(bottom_width / 2) - int(19 * text_iamge_height / 3),
                   border_width + ori_width - right_top_width - line_blank,
                   top_width + ori_height + int(bottom_width / 2) - int(14 * text_iamge_height / 3)),
                  fill=(128, 128, 128),
                  width=2) 

        origin_image.paste(logo, (border_width + ori_width - right_top_width - logo.width - 2 * line_blank, 
                       top_width + ori_height + int(bottom_width / 2) - int(9 * text_iamge_height / 2) - logo.height))
    else:
        text_block_height = top_width + ori_height + int(bottom_width / 2) - int(5 * text_iamge_height / 4)

        origin_image.paste(left_top, 
                           (border_width, 
                            top_width + ori_height + int(bottom_width / 2) - int(9 * text_iamge_height / 8))), 
        origin_image.paste(left_bottom, 
                           (border_width, 
                            top_width + ori_height + int(bottom_width / 2) + int(1 * text_iamge_height / 8)))
        origin_image.paste(right_top, 
                           (border_width + ori_width - right_top_width, 
                            top_width + ori_height + int(bottom_width / 2) - int(9 * text_iamge_height / 8)))
        origin_image.paste(right_bottom, 
                           (border_width + ori_width - right_top_width, 
                            top_width + ori_height + int(bottom_width / 2) + int(1 * text_iamge_height / 8)))    

        draw = ImageDraw.Draw(origin_image)

        draw.line((border_width + ori_width - right_top_width - line_blank,
                   top_width + ori_height + int(bottom_width / 2) - 1.8 * text_iamge_height / 2,
                   border_width + ori_width - right_top_width - line_blank,
                   top_width + ori_height + int(bottom_width / 2) + 2.3 * text_iamge_height / 2),
                  fill=(128, 128, 128),
                  width=2) 

        origin_image.paste(logo, (border_width + ori_width - right_top_width - logo.width - 2 * line_blank, 
                       text_block_height + int (text_iamge_height / logo_location_denominator)))
        
    return origin_image
    
    
