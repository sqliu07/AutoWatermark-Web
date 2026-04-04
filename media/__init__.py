"""media 包：Motion Photo / Ultra HDR / 视频处理。"""

from media.motion_photo import MotionPhotoSession, prepare_motion_photo
from media.ultrahdr import (
    split_ultrahdr,
    inject_xmp,
    update_primary_xmp_lengths,
    expand_gainmap_for_borders,
)

__all__ = [
    "MotionPhotoSession",
    "prepare_motion_photo",
    "split_ultrahdr",
    "inject_xmp",
    "update_primary_xmp_lengths",
    "expand_gainmap_for_borders",
]
