from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from PIL import Image


@dataclass
class RenderContext:
    """渲染上下文：由 generate_watermark_image 构建，传递给各渲染器。"""

    # 样式配置
    style: dict[str, Any]

    # 原始图像
    origin_image: Image.Image

    # 资源路径
    logo_path: Optional[str]
    font_path_thin: str
    font_path_bold: str
    font_path_regular: str
    font_path_symbol: str

    # EXIF 信息（已格式化）
    camera_info: list[str]
    shooting_info: list[str]

    # 布局计算结果
    landscape: bool
    footer_height: int
    font_size: int
    border_top: int
    border_left: int
    padding_x: int
    new_width: int
    new_height: int
    footer_center_y: float

    # 预渲染的文字块
    left_block: Optional[Image.Image] = None
    shooting_info_block: Optional[Image.Image] = None

    # 渲染输出（渲染器可写入以传递给后续流程）
    content_box: Optional[Tuple[int, int, int, int]] = None


class LayoutRenderer(ABC):
    """所有水印布局渲染器的抽象基类。"""

    @abstractmethod
    def render(self, context: RenderContext) -> Image.Image:
        """
        执行布局渲染，返回最终图像。

        职责：
        1. 创建或获取背景画布
        2. 在画布上绘制水印元素
        3. 如需要，设置 context.content_box
        4. 返回最终 Image
        """
        ...

    def create_background(self, context: RenderContext) -> Image.Image:
        """默认背景创建：基于 style["background"] 参数。子类可覆写。"""
        mode = context.style["background"]
        if mode == "frosted":
            from imaging.frosted_glass import create_frosted_glass_effect
            return create_frosted_glass_effect(context.origin_image)
        else:  # "white"
            canvas = Image.new("RGB", (context.new_width, context.new_height), "white")
            canvas.paste(context.origin_image, (context.border_left, context.border_top))
            return canvas

    def resolve_text_color(self, context: RenderContext) -> str:
        """根据 style["text_color_mode"] 解析文字颜色。"""
        mode = context.style["text_color_mode"]
        if mode == "auto_contrast":
            from imaging.image_ops import is_image_bright
            return "black" if is_image_bright(context.origin_image) else "white"
        return "black"
