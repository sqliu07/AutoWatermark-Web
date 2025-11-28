from constants import ImageConstants
from PIL import Image, ImageDraw, ImageFont, ImageOps
from logging_utils import get_logger

logger = get_logger("autowatermark.image_utils")

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
        logger.warning("Error resetting orientation: %s", e)
    return image

def image_resize(image, target_height):
    """
    图片/Logo缩放工具：将图片等比缩放到指定高度
    注意：不要用于文字图片！
    """
    if image.height == 0: return image
    aspect_ratio = image.width / image.height
    new_width = int(target_height * aspect_ratio)
    return image.resize((new_width, int(target_height)), Image.LANCZOS)

def text_to_image(text, font_path, font_size, color='black'):
    """
    直接使用确定的字号渲染文字
    """
    try:
        font = ImageFont.truetype(font_path, int(font_size))
    except Exception:
        font = ImageFont.load_default()
        
    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    
    bbox = font.getbbox(text)
    # 稍微加宽一点画布以免斜体被切
    text_width = bbox[2] - bbox[0] + int(font_size * 0.2)
    
    # 画布高度留足空间
    image = Image.new("RGBA", (text_width, int(line_height * 1.2)), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    
    draw.text((0, 0), text, font=font, fill=color)
    
    # 裁切掉多余的透明区域
    cropped = image.crop(image.getbbox())
    return cropped

def create_text_block(line1_text, line2_text, font_bold, font_thin, font_size):
    """
    将两行文字组合成一个块（用于样式 1 和 2）
    """
    img1 = text_to_image(line1_text, font_bold, font_size)
    img2 = text_to_image(line2_text, font_thin, font_size)
    
    # 上下两行间距：字号的 50%
    gap = int(font_size * 0.5)
    
    total_h = img1.height + gap + img2.height
    max_w = max(img1.width, img2.width)
    
    combined = Image.new("RGBA", (max_w, total_h), (255, 255, 255, 0))
    
    # 左对齐
    combined.paste(img1, (0, 0), img1)
    combined.paste(img2, (0, img1.height + gap), img2)
    
    return combined

def create_right_block(logo_path, text_block_img, footer_height, with_line=True, line_color=(128, 128, 128)):
    """
    组合右侧元素：[Logo] [竖线] [参数文字]
    """
    logo_target_height = int(footer_height * ImageConstants.LOGO_HEIGHT_RATIO)
    logo = Image.open(logo_path).convert("RGBA")
    logo = image_resize(logo, logo_target_height)
    
    # 元素水平间距：底栏高度的 20%
    spacing = int(footer_height * 0.2) 
    
    line_width = max(1, int(footer_height * 0.02)) 
    line_height = int(footer_height * 0.45) 
    
    if with_line:
        total_width = logo.width + spacing + line_width + spacing + text_block_img.width
    else:
        total_width = logo.width + spacing + text_block_img.width
        
    max_height = max(logo.height, text_block_img.height, line_height)
    combined = Image.new("RGBA", (total_width, max_height), (255, 255, 255, 0))
    
    current_x = 0
    
    # 1. 绘制 Logo (垂直居中)
    logo_y = (max_height - logo.height) // 2
    combined.paste(logo, (current_x, logo_y), logo)
    current_x += logo.width + spacing
    
    # 2. 绘制竖线 (垂直居中)
    if with_line:
        draw = ImageDraw.Draw(combined)
        line_y_start = (max_height - line_height) // 2
        draw.line(
            (current_x, line_y_start, current_x, line_y_start + line_height),
            fill=line_color,
            width=line_width
        )
        current_x += line_width + spacing
        
    # 3. 绘制文字块 (垂直居中)
    text_y = (max_height - text_block_img.height) // 2
    combined.paste(text_block_img, (current_x, text_y), text_block_img)
    
    return combined

def generate_watermark_image(origin_image, logo_path, camera_info, shooting_info,
                             font_path_thin, font_path_bold, watermark_type=1,
                             return_metadata=False, **kwargs):
    
    ori_width, ori_height = origin_image.size
    
    # 区分横竖构图的 footer 高度和字号策略
    if is_landscape(origin_image):
        footer_ratio = ImageConstants.FOOTER_RATIO_LANDSCAPE
        font_ratio = ImageConstants.FONT_SIZE_RATIO 
    else:
        footer_ratio = ImageConstants.FOOTER_RATIO_PORTRAIT
        # 竖构图字号缩小 25% 以防溢出
        font_ratio = ImageConstants.FONT_SIZE_RATIO * 0.75
        
    footer_height = int(ori_height * footer_ratio)
    
    font_size = int(footer_height * font_ratio)
    if font_size < 20: font_size = 20

    # === 关键修改：调整边框比例，实现 Polaroid 风格 ===
    # 0.25 的系数意味着顶部和侧边只有底栏高度的 1/4，形成明显的宽底边效果
    if watermark_type == 1:
        border_top = int(footer_height * 0.25)
        border_left = int(footer_height * 0.25)
        padding_x = border_left
    elif watermark_type == 2:
        border_top = 0
        border_left = 0
        padding_x = int(footer_height * 0.5)
    else:
        # Style 3 (Centered) 也使用 Polaroid 比例，或者您可以改回 0.8 做等宽
        # 这里统一改为 0.25 以保持“原本的留白感”
        border_top = int(footer_height * 0.25)
        border_left = int(footer_height * 0.25)
        padding_x = border_left

    new_width = ori_width + 2 * border_left
    new_height = ori_height + border_top + footer_height
    
    final_image = Image.new("RGB", (new_width, new_height), "white")
    final_image.paste(origin_image, (border_left, border_top))
    
    # 左侧：相机型号 (用于 Style 1 & 2)
    left_block = create_text_block(
        camera_info[0], camera_info[1], 
        font_path_bold, font_path_thin, 
        font_size
    )
    
    # 右侧：拍摄参数 (用于 Style 1 & 2)
    shooting_info_block = create_text_block(
        shooting_info[0], shooting_info[1], 
        font_path_bold, font_path_thin, 
        font_size
    )
    
    footer_center_y = border_top + ori_height + (footer_height / 2)
    
    if watermark_type == 3:
        # === 居中风格 (Style 3) ===
        # 布局：Logo 居中，下方只有一行拍摄参数
        
        logo_target_height = int(footer_height * 0.55) 
        logo = Image.open(logo_path).convert("RGBA")
        logo = image_resize(logo, logo_target_height)
        
        # 只生成参数文字 (Bold)
        center_text = text_to_image(shooting_info[0], font_path_bold, font_size)
        
        # 垂直堆叠 Logo 和 文字行
        v_gap = int(footer_height * 0.15)
        
        total_group_h = logo.height + v_gap + center_text.height
        total_group_w = max(logo.width, center_text.width)
        
        center_group = Image.new("RGBA", (total_group_w, total_group_h), (255, 255, 255, 0))
        
        # Logo 居中
        logo_x = (total_group_w - logo.width) // 2
        center_group.paste(logo, (logo_x, 0), logo)
        
        # 文字行居中
        text_x = (total_group_w - center_text.width) // 2
        center_group.paste(center_text, (text_x, logo.height + v_gap), center_text)
        
        # 4. 放置到画面底部中央
        pos_x = (new_width - center_group.width) // 2
        pos_y = int(footer_center_y - center_group.height / 2)
        final_image.paste(center_group, (pos_x, pos_y), center_group)

    else:
        # === 左右两端风格 (Style 1 & 2) ===
        right_group = create_right_block(logo_path, shooting_info_block, footer_height, with_line=True)
        
        # padding_x = border_left, 意味着文字和 Logo 会对齐照片的左右边缘
        left_x = padding_x
        left_y = int(footer_center_y - left_block.height / 2)
        final_image.paste(left_block, (left_x, left_y), left_block)
        
        right_x = new_width - padding_x - right_group.width
        right_y = int(footer_center_y - right_group.height / 2)
        final_image.paste(right_group, (right_x, right_y), right_group)

    if new_width % 2 != 0 or new_height % 2 != 0:
        final_image = ImageOps.expand(final_image, border=(0, 0, new_width % 2, new_height % 2), fill='white')

    if return_metadata:
        content_box = (border_left, border_top, border_left + ori_width, border_top + ori_height)
        overlay_image = final_image.copy().convert("RGBA")
        transparent = Image.new("RGBA", (ori_width, ori_height), (0,0,0,0))
        overlay_image.paste(transparent, (border_left, border_top))
        
        metadata = {
            "overlay_image": overlay_image,
            "content_box": content_box,
            "final_size": final_image.size,
        }
        return final_image, metadata

    return final_image