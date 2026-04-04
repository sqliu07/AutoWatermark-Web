from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from imaging.renderer_base import LayoutRenderer, RenderContext
from imaging.image_ops import image_resize
from imaging.text_rendering import text_to_image_with_symbol_font


class FilmFrameRenderer(LayoutRenderer):
    """胶片留白布局：独立画布，带阴影边框和居中 caption。"""

    def render(self, context: RenderContext) -> Image.Image:
        style = context.style
        origin = context.origin_image

        photo = origin.convert("RGB") if origin.mode != "RGB" else origin.copy()

        border_size = max(2, int(round(min(photo.size) * style["frame"]["border_ratio"])))
        framed_photo = ImageOps.expand(photo, border=border_size, fill="black")
        metrics = self._get_metrics(style, framed_photo)

        caption_group = self._create_caption_group(context, framed_photo, metrics)

        canvas_width = framed_photo.width + metrics["side_margin"] * 2
        canvas_height = (
            metrics["top_margin"]
            + framed_photo.height
            + metrics["text_gap"]
            + caption_group.height
            + metrics["bottom_margin"]
        )

        if style.get("frame", {}).get("force_square", False):
            canvas_side = max(canvas_width, canvas_height)
            canvas = Image.new("RGB", (canvas_side, canvas_side), metrics["background_color"])
            offset_x = (canvas_side - canvas_width) // 2
            offset_y = (canvas_side - canvas_height) // 2
        else:
            canvas = Image.new("RGB", (canvas_width, canvas_height), metrics["background_color"])
            offset_x = 0
            offset_y = 0

        photo_x = offset_x + (canvas_width - framed_photo.width) // 2
        photo_y = offset_y + metrics["top_margin"]
        shadow_blur = max(4, int(round(border_size * 2.5)))

        self._draw_shadow(canvas, framed_photo, photo_x, photo_y, shadow_blur)
        canvas.paste(framed_photo, (photo_x, photo_y))

        caption_x = offset_x + (canvas_width - caption_group.width) // 2
        caption_y = photo_y + framed_photo.height + metrics["text_gap"]
        canvas.paste(caption_group, (caption_x, caption_y), caption_group)

        context.content_box = (
            photo_x + border_size,
            photo_y + border_size,
            photo_x + border_size + photo.width,
            photo_y + border_size + photo.height,
        )

        return canvas

    @staticmethod
    def _get_metrics(style, framed_photo):
        fc = style["frame"]
        portrait = framed_photo.height > framed_photo.width
        min_side_margin = 52
        min_top_margin = 56
        min_text_gap = 56
        min_logo_gap = 12
        min_line_gap = 10
        min_bottom_margin = 72
        min_logo_height = 24
        min_font_size = 10
        min_font_start_size = 12
        logo_height_ratio = fc["logo_height_ratio_portrait"] if portrait else fc["logo_height_ratio"]
        font_size_ratio = fc["font_size_ratio_portrait"] if portrait else fc["font_size_ratio"]
        line_gap_ratio = fc["line_gap_ratio_portrait"] if portrait else fc["line_gap_ratio"]

        return {
            "background_color": fc["background_color"],
            "text_color": fc["text_color"],
            "border_size": max(2, int(round(min(framed_photo.size) * fc["border_ratio"]))),
            "side_margin": max(min_side_margin, int(round(framed_photo.width * fc["side_margin_ratio"]))),
            "top_margin": max(min_top_margin, int(round(framed_photo.height * fc["top_margin_ratio"]))),
            "text_gap": max(min_text_gap, int(round(framed_photo.height * fc["text_gap_ratio"]))),
            "logo_gap": max(min_logo_gap, int(round(framed_photo.width * fc["logo_gap_ratio"]))),
            "line_gap": max(min_line_gap, int(round(framed_photo.width * line_gap_ratio))),
            "bottom_margin": max(min_bottom_margin, int(round(framed_photo.height * fc["bottom_margin_ratio"]))),
            "logo_height": max(min_logo_height, int(round(framed_photo.height * logo_height_ratio))),
            "font_start_size": max(min_font_start_size, int(round(framed_photo.width * font_size_ratio))),
            "font_min_size": min_font_size,
            "font_max_width": max(100, int(round(framed_photo.width * fc["font_max_width_ratio"]))),
        }

    @staticmethod
    def _draw_shadow(canvas, framed_photo, photo_x, photo_y, blur_radius):
        shadow_alpha = 85
        shadow_padding_multiplier = 3
        shadow_x_offset_divisor = 2

        shadow_padding = blur_radius * shadow_padding_multiplier
        shadow = Image.new(
            "RGBA",
            (
                framed_photo.width + shadow_padding * 2,
                framed_photo.height + shadow_padding * 2,
            ),
            (0, 0, 0, 0),
        )
        shadow_draw = ImageDraw.Draw(shadow)
        rect = (
            shadow_padding,
            shadow_padding,
            shadow_padding + framed_photo.width,
            shadow_padding + framed_photo.height,
        )
        shadow_draw.rectangle(rect, fill=(0, 0, 0, shadow_alpha))
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

        shadow_x = photo_x - shadow_padding + max(1, blur_radius // shadow_x_offset_divisor)
        shadow_y = photo_y - shadow_padding + blur_radius
        canvas.paste(shadow, (shadow_x, shadow_y), shadow)

    @staticmethod
    def _fit_text_font_size(text_lines, font_path, start_size, min_size, max_width):
        lo = max(1, int(min_size))
        hi = max(lo, int(start_size))

        def _fits(size):
            try:
                font = ImageFont.truetype(font_path, int(size))
            except Exception:
                font = ImageFont.load_default()
            for line in text_lines:
                if not line:
                    continue
                bbox = font.getbbox(line)
                width = bbox[2] - bbox[0] + int(size * 0.2)
                if width > max_width:
                    return False
            return True

        if _fits(hi):
            return hi

        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _fits(mid):
                lo = mid
            else:
                hi = mid - 1

        return lo

    def _create_caption_group(self, context: RenderContext, framed_photo, metrics):
        logo_target_height = metrics["logo_height"]
        with Image.open(context.logo_path) as _logo_raw:
            logo_image = _logo_raw.convert("RGBA")
        logo_image = image_resize(logo_image, logo_target_height)

        caption_lines = [
            context.camera_info[1] if len(context.camera_info) > 1 else "",
            context.camera_info[0] if len(context.camera_info) > 0 else "",
            context.shooting_info[0] if len(context.shooting_info) > 0 else "",
        ]
        caption_lines = [line for line in caption_lines if line]

        caption_font_size = self._fit_text_font_size(
            caption_lines,
            context.font_path_regular,
            start_size=metrics["font_start_size"],
            min_size=metrics["font_min_size"],
            max_width=metrics["font_max_width"],
        )
        caption_images = [
            text_to_image_with_symbol_font(
                line,
                context.font_path_regular,
                caption_font_size,
                metrics["text_color"],
                symbol_font_path=context.font_path_symbol,
            )
            for line in caption_lines
        ]

        logo_gap = metrics["logo_gap"]
        line_gap = metrics["line_gap"]
        group_width = max([logo_image.width] + [image.width for image in caption_images])
        group_height = logo_image.height + logo_gap + sum(image.height for image in caption_images)
        if len(caption_images) > 1:
            group_height += line_gap * (len(caption_images) - 1)

        caption_group = Image.new("RGBA", (group_width, group_height), (255, 255, 255, 0))
        current_y = 0

        logo_x = (group_width - logo_image.width) // 2
        caption_group.paste(logo_image, (logo_x, current_y), logo_image)
        current_y += logo_image.height + logo_gap

        for caption_image in caption_images:
            caption_x = (group_width - caption_image.width) // 2
            caption_group.paste(caption_image, (caption_x, current_y), caption_image)
            current_y += caption_image.height + line_gap

        return caption_group
