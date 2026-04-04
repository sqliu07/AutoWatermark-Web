from PIL import Image, ImageDraw, ImageFilter
from constants import ImageConstants
from imaging.image_ops import is_landscape, _darken_rgb_inplace


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
