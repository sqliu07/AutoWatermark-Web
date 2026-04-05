from PIL import Image, ImageDraw, ImageFont
from constants import ImageConstants
from imaging.image_ops import image_resize


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


def text_to_image_with_symbol_font(text, font_path, font_size, color, symbol_font_path=None, symbol_char="\u0192"):
    """
    针对特定字符单独使用另一套字体渲染，避免等宽字体里的字形过于突兀。
    """
    if not text or not symbol_font_path or symbol_char not in text:
        return text_to_image(text, font_path, font_size, color)

    try:
        primary_font = ImageFont.truetype(font_path, int(font_size))
        symbol_font = ImageFont.truetype(symbol_font_path, int(font_size))
    except Exception:
        return text_to_image(text, font_path, font_size, color)

    segments = []
    current_text = []
    current_is_symbol = None

    for char in text:
        is_symbol = char == symbol_char
        if current_is_symbol is None:
            current_is_symbol = is_symbol
        if is_symbol != current_is_symbol:
            segments.append(("".join(current_text), symbol_font if current_is_symbol else primary_font))
            current_text = [char]
            current_is_symbol = is_symbol
        else:
            current_text.append(char)

    if current_text:
        segments.append(("".join(current_text), symbol_font if current_is_symbol else primary_font))

    max_ascent = max(font.getmetrics()[0] for _, font in segments)
    max_descent = max(font.getmetrics()[1] for _, font in segments)
    line_height = max_ascent + max_descent

    total_width = 0
    for segment_text, segment_font in segments:
        bbox = segment_font.getbbox(segment_text)
        total_width += (bbox[2] - bbox[0])

    total_width += int(font_size * 0.2)
    image = Image.new("RGBA", (max(1, total_width), int(line_height * 1.2)), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    current_x = 0
    for segment_text, segment_font in segments:
        bbox = segment_font.getbbox(segment_text)
        segment_width = bbox[2] - bbox[0]
        ascent, _ = segment_font.getmetrics()
        y = max_ascent - ascent
        draw.text((current_x, y), segment_text, font=segment_font, fill=color)
        current_x += segment_width

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
    with Image.open(logo_path) as _logo_raw:
        logo = _logo_raw.convert("RGBA")
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
