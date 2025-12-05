from constants import ImageConstants
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageStat
from logging_utils import get_logger

logger = get_logger("autowatermark.image_utils")

def is_landscape(image):
    return image.width >= image.height

def is_image_bright(image, threshold=ImageConstants.WATERMARK_GLASS_BG_THRESHOLD):
    """
    判断图片是否为浅色背景
    :param threshold: 亮度阈值 (0-255)，默认 130。大于此值认为背景是亮的，需要用深色字。
    :return: True (亮背景) / False (暗背景)
    """
    # 转换为灰度图
    gray_img = image.convert("L")
    # 使用 ImageStat 计算平均亮度
    stat = ImageStat.Stat(gray_img)
    avg_brightness = stat.mean[0]
    logger.info("Current image avg brightness: %s", str(avg_brightness))

    return avg_brightness > threshold
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
    """
    if image.height == 0: return image
    aspect_ratio = image.width / image.height
    new_width = int(target_height * aspect_ratio)
    return image.resize((new_width, int(target_height)), Image.LANCZOS)

def text_to_image(text, font_path, font_size, color):
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
    img1 = text_to_image(line1_text, font_bold, font_size, 'black')
    img2 = text_to_image(line2_text, font_thin, font_size, 'black')

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

def create_rounded_rectangle_mask(size, radius):
    factor = 4
    large_size = (size[0] * factor, size[1] * factor)
    large_radius = radius * factor

    mask = Image.new('L', large_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), large_size], radius=large_radius, fill=255)

    return mask.resize(size, Image.Resampling.LANCZOS)

def create_frosted_glass_effect(origin_image):
    ori_w, ori_h = origin_image.size
    min_dim = min(ori_w, ori_h)

    bg_scale = ImageConstants.WATERMARK_GLASS_BG_SCALE
    shadow_scale_factor = ImageConstants.WATERMARK_GLASS_SHADOW_SCALE

    corner_radius = int(min_dim * ImageConstants.WATERMARK_GLASS_CORNER_RADIUS_FACTOR)

    shadow_blur_radius = int(min_dim * ImageConstants.WATERMARK_GLASS_BLUR_RADIUS)

    shadow_offset_y = int(min_dim * 0.05)
    if is_landscape(origin_image):
        shadow_offset_y = int(min_dim * 0.03)
    # 阴影颜色 (纯黑，透明度 40%) - 加深
    shadow_color = (0, 0, 0, ImageConstants.WATERMARK_GLASS_COLOR)

    canvas_w = int(ori_w * bg_scale)
    if is_landscape(origin_image):
        canvas_w = int(canvas_w * 0.95)
    canvas_h = int(ori_h * bg_scale)
    canvas_size = (canvas_w, canvas_h)
    small_bg = origin_image.convert("RGB").resize(
        (canvas_w // 10, canvas_h // 10),
        Image.Resampling.BILINEAR
    )
    # 模糊
    blurred_bg = small_bg.filter(ImageFilter.GaussianBlur(8))
    # 放大铺满
    final_bg = blurred_bg.resize(canvas_size, Image.Resampling.LANCZOS)

    dim_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 20))
    final_bg = Image.alpha_composite(final_bg.convert("RGBA"), dim_layer).convert("RGB")


    mask = create_rounded_rectangle_mask((ori_w, ori_h), corner_radius)
    foreground = origin_image.copy()
    foreground.putalpha(mask)


    shadow_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)


    pos_x = (canvas_w - ori_w) // 2
    pos_y = (canvas_h - ori_h) // 2

    shadow_w = int(ori_w * shadow_scale_factor)
    shadow_h = int(ori_h * shadow_scale_factor)

    shadow_x = pos_x + (ori_w - shadow_w) // 2

    shadow_y = pos_y + (ori_h - shadow_h) // 2 - shadow_offset_y

    shadow_rect = [
        (shadow_x, shadow_y),
        (shadow_x + shadow_w, shadow_y + shadow_h)
    ]

    shadow_draw.rounded_rectangle(shadow_rect, radius=corner_radius, fill=shadow_color)

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur_radius))

    final_image = final_bg.convert("RGBA")

    final_image = Image.alpha_composite(final_image, shadow_layer)

    final_image.paste(foreground, (pos_x, pos_y - shadow_offset_y), foreground)

    final_image = final_image.convert("RGB")

    return final_image
def generate_watermark_image(origin_image, logo_path, camera_info, shooting_info,
                             font_path_thin, font_path_bold, watermark_type=1,
                             return_metadata=False, **kwargs):

    logger.info("Generating watermark, current watermark type: %s", watermark_type)
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

    if watermark_type != 4:
        final_image = Image.new("RGB", (new_width, new_height), "white")
        final_image.paste(origin_image, (border_left, border_top))
    else:
        final_image = create_frosted_glass_effect(origin_image)

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

    if watermark_type == 3 or watermark_type == 4:
        # === 居中风格 (Style 3) ===
        # 布局：Logo 居中，下方只有一行拍摄参数

        logo_target_height = int(footer_height * 0.55)
        logo = Image.open(logo_path).convert("RGBA")
        logo = image_resize(logo, logo_target_height)

        # 只生成参数文字 (Bold)
        center_text = text_to_image(shooting_info[0], font_path_bold, font_size, 'black')

        if watermark_type == 4:
            text_color = 'white'
            if is_image_bright(origin_image):
                text_color = 'black'
            center_text = text_to_image(shooting_info[0], font_path_bold, font_size, text_color)

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
        if watermark_type == 4:
            pos_x = (final_image.width - center_group.width) // 2
            pos_y = final_image.height - center_group.height - center_group.height // 4
            if is_landscape(origin_image):
                pos_y = final_image.height - center_group.height - center_group.height // 6
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