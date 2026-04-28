from PIL import Image, ImageOps

from constants import CommonConstants
from imaging.image_ops import is_landscape
from imaging.renderer_base import RenderContext
from imaging.renderer_registry import get_renderer
from imaging.text_rendering import create_text_block
from logging_utils import get_logger
from services.watermark_styles import get_style, load_cached_watermark_styles

logger = get_logger("autowatermark.watermark")


def generate_watermark_image(origin_image, logo_path, camera_info, shooting_info,
                             font_path_thin, font_path_bold, watermark_type=1,
                             return_metadata=False, style_config=None, style=None,
                             font_path_regular=None, font_path_symbol=None):
    if font_path_regular is None:
        font_path_regular = font_path_bold
    if font_path_symbol is None:
        font_path_symbol = font_path_thin
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

    # padding_x 内联解析（替代 _PADDING_X_RESOLVERS dict）
    padding_x_mode = style["padding_x_mode"]
    if padding_x_mode == "footer_ratio":
        padding_x = int(footer_height * style["padding_x_ratio"])
    else:  # "border_left"
        padding_x = border_left

    new_width = ori_width + 2 * border_left
    new_height = ori_height + border_top + footer_height

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

    # 构建 RenderContext
    context = RenderContext(
        style=style,
        origin_image=origin_image,
        logo_path=logo_path,
        font_path_thin=font_path_thin,
        font_path_bold=font_path_bold,
        font_path_regular=font_path_regular,
        font_path_symbol=font_path_symbol,
        camera_info=camera_info,
        shooting_info=shooting_info,
        landscape=landscape,
        footer_height=footer_height,
        font_size=font_size,
        border_top=border_top,
        border_left=border_left,
        padding_x=padding_x,
        new_width=new_width,
        new_height=new_height,
        footer_center_y=footer_center_y,
        left_block=left_block,
        shooting_info_block=shooting_info_block,
    )

    # 通过注册表获取渲染器
    renderer = get_renderer(style["layout"])
    final_image = renderer.render(context)

    # 尺寸对齐（偶数化）
    final_width, final_height = final_image.size
    if final_width % 2 != 0 or final_height % 2 != 0:
        final_image = ImageOps.expand(
            final_image,
            border=(0, 0, final_width % 2, final_height % 2),
            fill='white',
        )

    if return_metadata:
        content_box = context.content_box or (border_left, border_top, border_left + ori_width, border_top + ori_height)
        overlay_image = final_image.copy().convert("RGBA")
        transparent = Image.new("RGBA", (content_box[2] - content_box[0], content_box[3] - content_box[1]), (0, 0, 0, 0))
        overlay_image.paste(transparent, (content_box[0], content_box[1]))

        metadata = {
            "overlay_image": overlay_image,
            "content_box": content_box,
            "final_size": final_image.size,
        }
        return final_image, metadata

    return final_image
