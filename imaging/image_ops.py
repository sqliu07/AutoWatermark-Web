from functools import lru_cache
import piexif
from PIL import Image, ImageDraw, ImageStat
from constants import ImageConstants
from logging_utils import get_logger

Image.MAX_IMAGE_PIXELS = ImageConstants.MAX_IMAGE_PIXELS

logger = get_logger("autowatermark.image_ops")


def is_landscape(image):
    return image.width >= image.height


def is_image_bright(image, threshold=ImageConstants.WATERMARK_GLASS_BG_THRESHOLD):
    """
    判断图片是否为浅色背景
    :param threshold: 亮度阈值 (0-255)，默认 130。大于此值认为背景是亮的，需要用深色字。
    :return: True (亮背景) / False (暗背景)
    为了避免误判，同时判断图片下半部分的亮度
    """
    gray_img = image.convert("L")
    try:
        stat = ImageStat.Stat(gray_img)
        avg_brightness = stat.mean[0]
        logger.info("Current image avg brightness: %s", str(avg_brightness))
    finally:
        gray_img.close()

    w, h = image.size
    bottom_half = image.crop((0, h // 2, w, h))
    try:
        gray_half = bottom_half.convert("L")
        try:
            stat = ImageStat.Stat(gray_half)
            avg_brightness_half = stat.mean[0]
            logger.info("Bottom-half avg brightness: %s", str(avg_brightness_half))
        finally:
            gray_half.close()
    finally:
        bottom_half.close()

    return avg_brightness > threshold and avg_brightness_half > threshold


def reset_image_orientation(image):
    try:
        exif = image._getexif()
        if exif:
            orientation = exif.get(piexif.ImageIFD.Orientation)
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
    if image.height == 0:
        return image
    aspect_ratio = image.width / image.height
    new_width = int(target_height * aspect_ratio)
    return image.resize((new_width, int(target_height)), Image.LANCZOS)


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
