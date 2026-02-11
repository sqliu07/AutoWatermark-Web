from constants import CommonConstants, ImageConstants
from services.watermark_styles import get_style, load_cached_watermark_styles

from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageStat
from logging_utils import get_logger

Image.MAX_IMAGE_PIXELS = ImageConstants.MAX_IMAGE_PIXELS

logger = get_logger("autowatermark.image_utils")

def is_landscape(image):
    return image.width >= image.height

def is_image_bright(image, threshold=ImageConstants.WATERMARK_GLASS_BG_THRESHOLD):
    """
    判断图片是否为浅色背景
    :param threshold: 亮度阈值 (0-255)，默认 130。大于此值认为背景是亮的，需要用深色字。
    :return: True (亮背景) / False (暗背景)
    为了避免误判，同时判断图片下半部分的亮度
    """
    # 转换为灰度图
    gray_img = image.convert("L")
    # 使用 ImageStat 计算平均亮度
    stat = ImageStat.Stat(gray_img)
    avg_brightness = stat.mean[0]
    logger.info("Current image avg brightness: %s", str(avg_brightness))

    w, h = image.size
    bottom_half = image.crop((0, h // 2, w, h))
    gray_img = bottom_half.convert("L")
    stat = ImageStat.Stat(gray_img)
    avg_brightness_half = stat.mean[0]
    logger.info("Bottom-half avg brightness: %s", str(avg_brightness_half))

    return avg_brightness > threshold and avg_brightness_half > threshold
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

@lru_cache(maxsize=64)
def _rounded_mask_cached(w: int, h: int, radius: int, aa: int) -> Image.Image:
    aa = max(1, int(aa))
    radius = max(0, int(radius))

    W, H = w * aa, h * aa
    R = radius * aa

    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, W - 1, H - 1), radius=R, fill=255)

    if aa == 1:
        return mask.copy()

    return mask.resize((w, h), Image.Resampling.BILINEAR)

def create_rounded_rectangle_mask(size, radius, aa=2):
    w, h = size
    return _rounded_mask_cached(int(w), int(h), int(radius), int(aa))

def _darken_rgb_inplace(img_rgb: Image.Image, dim_alpha_0_255: int) -> Image.Image:
    """
    用 point 做线性变暗：out = in * (1 - dim_alpha/255)
    不创建额外的全尺寸黑图，内存更省。
    """
    dim_alpha_0_255 = max(0, min(255, int(dim_alpha_0_255)))
    if dim_alpha_0_255 == 0:
        return img_rgb
    k = 1.0 - (dim_alpha_0_255 / 255.0)

    lut = [int(i * k) for i in range(256)]
    return img_rgb.point(lut * 3)

def create_frosted_glass_effect(origin_image):
    ori_w, ori_h = origin_image.size
    min_dim = min(ori_w, ori_h)

    bg_scale = ImageConstants.WATERMARK_GLASS_BG_SCALE
    shadow_scale_factor = ImageConstants.WATERMARK_GLASS_SHADOW_SCALE

    landscape = is_landscape(origin_image)

    corner_radius = int(min_dim * ImageConstants.WATERMARK_GLASS_CORNER_RADIUS_FACTOR)
    shadow_blur_radius = int(min_dim * ImageConstants.WATERMARK_GLASS_BLUR_RADIUS)

    shadow_offset_y = int(min_dim * (0.03 if landscape else 0.05))
    shadow_color = (0, 0, 0, ImageConstants.WATERMARK_GLASS_COLOR)

    canvas_w = int(ori_w * bg_scale * (0.95 if landscape else 1.0))
    canvas_h = int(ori_h * bg_scale)
    canvas_size = (canvas_w, canvas_h)

    ds_w = max(1, canvas_w // 10)
    ds_h = max(1, canvas_h // 10)

    if origin_image.mode != "RGB":
        small_bg_source = origin_image.convert("RGB")
    else:
        small_bg_source = origin_image
    small_bg = small_bg_source.resize((ds_w, ds_h), Image.Resampling.BOX)

    blurred_bg = small_bg.filter(ImageFilter.GaussianBlur(8))
    # 放大铺满
    final_bg = blurred_bg.resize(canvas_size, Image.Resampling.LANCZOS)
    del small_bg

    final_bg = _darken_rgb_inplace(final_bg, dim_alpha_0_255=20)

    if origin_image.mode != "RGB":
        foreground_rgb = origin_image.convert("RGB")
    else:
        foreground_rgb = origin_image

    pos_x = (canvas_w - ori_w) // 2
    pos_y = (canvas_h - ori_h) // 2

    shadow_w = int(ori_w * shadow_scale_factor)
    shadow_h = int(ori_h * shadow_scale_factor)
    shadow_x = pos_x + (ori_w - shadow_w) // 2
    shadow_y = pos_y + (ori_h - shadow_h) // 2 - shadow_offset_y

    pad = int(shadow_blur_radius * 1.2)

    x0 = max(0, shadow_x - pad)
    y0 = max(0, shadow_y - pad)
    x1 = min(canvas_w, shadow_x + shadow_w + pad)
    y1 = min(canvas_h, shadow_y + shadow_h + pad)

    patch_w = max(1, x1 - x0)
    patch_h = max(1, y1 - y0)

    shadow_patch = Image.new("RGBA", (patch_w, patch_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow_patch)

    rx0 = shadow_x - x0
    ry0 = shadow_y - y0
    rx1 = rx0 + shadow_w
    ry1 = ry0 + shadow_h
    d.rounded_rectangle((rx0, ry0, rx1, ry1), radius=corner_radius, fill=shadow_color)

    if shadow_blur_radius > 0:
        shadow_patch = shadow_patch.filter(ImageFilter.BoxBlur(shadow_blur_radius))

    final_image = final_bg
    del final_bg

    final_image.paste(shadow_patch, (x0, y0), shadow_patch)
    del shadow_patch

    fg_x = pos_x
    fg_y = pos_y - shadow_offset_y
    corner_radius = max(0, min(corner_radius, ori_w // 2, ori_h // 2))
    if corner_radius > 0:
        bg_tl = final_image.crop((fg_x, fg_y, fg_x + corner_radius, fg_y + corner_radius))
        bg_tr = final_image.crop((fg_x + ori_w - corner_radius, fg_y, fg_x + ori_w, fg_y + corner_radius))
        bg_bl = final_image.crop((fg_x, fg_y + ori_h - corner_radius, fg_x + corner_radius, fg_y + ori_h))
        bg_br = final_image.crop((fg_x + ori_w - corner_radius, fg_y + ori_h - corner_radius, fg_x + ori_w, fg_y + ori_h))

        corner_mask = Image.new("L", (corner_radius, corner_radius), 255)
        corner_draw = ImageDraw.Draw(corner_mask)
        corner_draw.pieslice((0, 0, corner_radius * 2, corner_radius * 2), 180, 270, fill=0)
        corner_mask_tr = corner_mask.transpose(Image.FLIP_LEFT_RIGHT)
        corner_mask_bl = corner_mask.transpose(Image.FLIP_TOP_BOTTOM)
        corner_mask_br = corner_mask.transpose(Image.ROTATE_180)

    final_image.paste(foreground_rgb, (fg_x, fg_y))
    del foreground_rgb

    if corner_radius > 0:
        final_image.paste(bg_tl, (fg_x, fg_y), corner_mask)
        final_image.paste(bg_tr, (fg_x + ori_w - corner_radius, fg_y), corner_mask_tr)
        final_image.paste(bg_bl, (fg_x, fg_y + ori_h - corner_radius), corner_mask_bl)
        final_image.paste(bg_br, (fg_x + ori_w - corner_radius, fg_y + ori_h - corner_radius), corner_mask_br)
        del bg_tl
        del bg_tr
        del bg_bl
        del bg_br
        del corner_mask
        del corner_mask_tr
        del corner_mask_bl
        del corner_mask_br

    return final_image


def _padding_from_border_left(_footer_height, border_left, _style):
    return border_left


def _padding_from_footer_ratio(footer_height, _border_left, style):
    return int(footer_height * style["padding_x_ratio"])


_PADDING_X_RESOLVERS = {
    "border_left": _padding_from_border_left,
    "footer_ratio": _padding_from_footer_ratio,
}


def _render_background_white(origin_image, new_width, new_height, border_left, border_top):
    final_image = Image.new("RGB", (new_width, new_height), "white")
    final_image.paste(origin_image, (border_left, border_top))
    return final_image


def _render_background_frosted(origin_image, _new_width, _new_height, _border_left, _border_top):
    return create_frosted_glass_effect(origin_image)


_BACKGROUND_RENDERERS = {
    "white": _render_background_white,
    "frosted": _render_background_frosted,
}


def _text_color_black(_origin_image):
    return "black"


def _text_color_auto_contrast(origin_image):
    return "black" if is_image_bright(origin_image) else "white"


_TEXT_COLOR_RESOLVERS = {
    "black": _text_color_black,
    "auto_contrast": _text_color_auto_contrast,
}


def _center_position_footer_center(context):
    center_group = context["center_group"]
    pos_x = (context["new_width"] - center_group.width) // 2
    pos_y = int(context["footer_center_y"] - center_group.height / 2)
    return pos_x, pos_y


def _center_position_bottom_offset(context):
    center_group = context["center_group"]
    style = context["style"]
    landscape = context["landscape"]
    final_image = context["final_image"]

    pos_x = (final_image.width - center_group.width) // 2
    if landscape:
        divisor = int(style["bottom_offset_landscape_divisor"])
    else:
        divisor = int(style["bottom_offset_portrait_divisor"])
    divisor = max(1, divisor)
    pos_y = final_image.height - center_group.height - max(1, center_group.height // divisor)
    return pos_x, pos_y


_CENTER_POSITION_RESOLVERS = {
    "footer_center": _center_position_footer_center,
    "bottom_offset": _center_position_bottom_offset,
}


def _render_layout_center_stack(final_image, context):
    style = context["style"]
    footer_height = context["footer_height"]
    logo_path = context["logo_path"]
    shooting_info = context["shooting_info"]
    font_path_bold = context["font_path_bold"]
    font_size = context["font_size"]
    origin_image = context["origin_image"]

    logo_target_height = int(footer_height * style["center_logo_ratio"])
    logo = Image.open(logo_path).convert("RGBA")
    logo = image_resize(logo, logo_target_height)

    text_color = _TEXT_COLOR_RESOLVERS[style["text_color_mode"]](origin_image)
    center_text = text_to_image(shooting_info[0], font_path_bold, font_size, text_color)

    v_gap = int(footer_height * style["center_gap_ratio"])
    total_group_h = logo.height + v_gap + center_text.height
    total_group_w = max(logo.width, center_text.width)
    center_group = Image.new("RGBA", (total_group_w, total_group_h), (255, 255, 255, 0))

    logo_x = (total_group_w - logo.width) // 2
    center_group.paste(logo, (logo_x, 0), logo)

    text_x = (total_group_w - center_text.width) // 2
    center_group.paste(center_text, (text_x, logo.height + v_gap), center_text)

    position_context = dict(context)
    position_context["center_group"] = center_group
    pos_x, pos_y = _CENTER_POSITION_RESOLVERS[style["position_mode"]](position_context)
    final_image.paste(center_group, (pos_x, pos_y), center_group)


def _render_layout_split_lr(final_image, context):
    style = context["style"]
    footer_height = context["footer_height"]
    logo_path = context["logo_path"]
    shooting_info_block = context["shooting_info_block"]
    left_block = context["left_block"]
    footer_center_y = context["footer_center_y"]
    padding_x = context["padding_x"]
    new_width = context["new_width"]

    right_group = create_right_block(
        logo_path,
        shooting_info_block,
        footer_height,
        with_line=style["right_divider_line"],
    )

    left_x = padding_x
    left_y = int(footer_center_y - left_block.height / 2)
    final_image.paste(left_block, (left_x, left_y), left_block)

    right_x = new_width - padding_x - right_group.width
    right_y = int(footer_center_y - right_group.height / 2)
    final_image.paste(right_group, (right_x, right_y), right_group)


_LAYOUT_RENDERERS = {
    "center_stack": _render_layout_center_stack,
    "split_lr": _render_layout_split_lr,
}


def generate_watermark_image(origin_image, logo_path, camera_info, shooting_info,
                             font_path_thin, font_path_bold, watermark_type=1,
                             return_metadata=False, **kwargs):
    style_config = kwargs.get("style_config")
    style = kwargs.get("style")
    if style_config is None:
        style_config = load_cached_watermark_styles(CommonConstants.WATERMARK_STYLE_CONFIG_PATH)
    if style is None:
        style = get_style(style_config, watermark_type)
    if not style or not style["enabled"]:
        raise ValueError(f"Invalid watermark style: {watermark_type}")

    global_style = style_config["global"]

    logger.info("Generating watermark, current watermark type: %s", style["style_id"])
    ori_width, ori_height = origin_image.size
    landscape = is_landscape(origin_image)

    if landscape:
        footer_ratio = global_style["footer_ratio_landscape"]
        font_ratio = global_style["font_size_ratio"]
    else:
        footer_ratio = global_style["footer_ratio_portrait"]
        font_ratio = global_style["font_size_ratio"] * global_style["portrait_font_scale"]

    footer_height = int(ori_height * footer_ratio)
    font_size = int(footer_height * font_ratio)
    min_font_size = int(global_style["min_font_size"])
    if font_size < min_font_size:
        font_size = min_font_size

    border_top = int(footer_height * style["border_top_ratio"])
    border_left = int(footer_height * style["border_left_ratio"])
    padding_x = _PADDING_X_RESOLVERS[style["padding_x_mode"]](footer_height, border_left, style)

    new_width = ori_width + 2 * border_left
    new_height = ori_height + border_top + footer_height

    final_image = _BACKGROUND_RENDERERS[style["background"]](
        origin_image, new_width, new_height, border_left, border_top
    )

    left_block = create_text_block(
        camera_info[0], camera_info[1],
        font_path_bold, font_path_thin,
        font_size
    )

    shooting_info_block = create_text_block(
        shooting_info[0], shooting_info[1],
        font_path_bold, font_path_thin,
        font_size
    )

    footer_center_y = border_top + ori_height + (footer_height / 2)

    layout_context = {
        "style": style,
        "origin_image": origin_image,
        "final_image": final_image,
        "logo_path": logo_path,
        "shooting_info": shooting_info,
        "font_path_bold": font_path_bold,
        "font_size": font_size,
        "footer_height": footer_height,
        "footer_center_y": footer_center_y,
        "left_block": left_block,
        "shooting_info_block": shooting_info_block,
        "padding_x": padding_x,
        "new_width": new_width,
        "landscape": landscape,
    }
    _LAYOUT_RENDERERS[style["layout"]](final_image, layout_context)

    final_width, final_height = final_image.size
    if final_width % 2 != 0 or final_height % 2 != 0:
        final_image = ImageOps.expand(
            final_image,
            border=(0, 0, final_width % 2, final_height % 2),
            fill='white',
        )

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
