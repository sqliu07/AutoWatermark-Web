from PIL import Image

from imaging.renderer_base import LayoutRenderer, RenderContext
from imaging.image_ops import image_resize
from imaging.text_rendering import text_to_image


class CenterStackRenderer(LayoutRenderer):
    """居中堆叠布局：Logo + 参数文字垂直居中。"""

    def render(self, context: RenderContext) -> Image.Image:
        style = context.style
        final_image = self.create_background(context)

        # Logo
        logo_target_height = int(context.footer_height * style["center_logo_ratio"])
        with Image.open(context.logo_path) as _logo_raw:
            logo = _logo_raw.convert("RGBA")
        logo = image_resize(logo, logo_target_height)

        # 文字
        text_color = self.resolve_text_color(context)
        center_text = text_to_image(
            context.shooting_info[0], context.font_path_bold, context.font_size, text_color
        )

        # 组装 center_group
        v_gap = int(context.footer_height * style["center_gap_ratio"])
        total_group_h = logo.height + v_gap + center_text.height
        total_group_w = max(logo.width, center_text.width)
        center_group = Image.new("RGBA", (total_group_w, total_group_h), (255, 255, 255, 0))

        logo_x = (total_group_w - logo.width) // 2
        center_group.paste(logo, (logo_x, 0), logo)

        text_x = (total_group_w - center_text.width) // 2
        center_group.paste(center_text, (text_x, logo.height + v_gap), center_text)

        # 定位
        pos_x, pos_y = self._resolve_position(context, center_group, final_image)
        final_image.paste(center_group, (pos_x, pos_y), center_group)

        return final_image

    @staticmethod
    def _resolve_position(
        context: RenderContext, center_group: Image.Image, final_image: Image.Image
    ) -> tuple[int, int]:
        mode = context.style["position_mode"]

        if mode == "bottom_offset":
            style = context.style
            pos_x = (final_image.width - center_group.width) // 2
            divisor = int(
                style["bottom_offset_landscape_divisor"]
                if context.landscape
                else style["bottom_offset_portrait_divisor"]
            )
            divisor = max(1, divisor)
            pos_y = final_image.height - center_group.height - max(1, center_group.height // divisor)
            return pos_x, pos_y
        else:  # "footer_center"
            pos_x = (context.new_width - center_group.width) // 2
            pos_y = int(context.footer_center_y - center_group.height / 2)
            return pos_x, pos_y
