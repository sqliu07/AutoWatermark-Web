"""process_image() 的统一返回类型。"""
from dataclasses import dataclass
from typing import Optional
from PIL import Image


@dataclass
class ProcessResult:
    """处理结果。"""
    success: bool = True
    is_motion: bool = False
    preview_image: Optional[Image.Image] = None
