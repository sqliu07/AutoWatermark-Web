from PIL import Image

from imaging.renderer_base import LayoutRenderer, RenderContext
from imaging.text_rendering import create_right_block


class SplitLRRenderer(LayoutRenderer):
    """左右分栏布局：左侧机型文字 + 右侧 Logo | 竖线 | 参数文字。"""

    def render(self, context: RenderContext) -> Image.Image:
        final_image = self.create_background(context)

        right_group = create_right_block(
            context.logo_path,
            context.shooting_info_block,
            context.footer_height,
            with_line=context.style["right_divider_line"],
        )

        left_x = context.padding_x
        left_y = int(context.footer_center_y - context.left_block.height / 2)
        final_image.paste(context.left_block, (left_x, left_y), context.left_block)

        right_x = context.new_width - context.padding_x - right_group.width
        right_y = int(context.footer_center_y - right_group.height / 2)
        final_image.paste(right_group, (right_x, right_y), right_group)

        return final_image
