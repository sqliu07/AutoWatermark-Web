"""media 包：Motion Photo / Ultra HDR / 视频处理工具集。"""

from media.xmp import (
    XMP_START_MARKER,
    XMP_END_MARKER,
    XMP_HEADER,
    MICRO_VIDEO_OFFSET_PATTERN,
    MICRO_VIDEO_LENGTH_PATTERN,
    MOTIONPHOTO_FLAG_PATTERN,
    OFFSET_ATTRS,
    LENGTH_ATTRS,
    _extract_xmp_segment,
    _parse_first_match,
    _looks_like_motionphoto_flag,
    _update_container_directory_lengths,
    _ensure_container_namespaces,
    _detect_motion_video_mime,
    _ensure_hdrgm_namespace_and_version,
    _set_container_directory_ultrahdr_motion,
    _prepare_xmp_ultrahdr_motion,
    _prepare_xmp,
    _update_attribute_if_exists,
    _ensure_offset_length_attrs,
    _strip_existing_xmp,
    _build_xmp_segment,
    _inject_xmp,
)

from media.video import (
    _copy_all_metadata_with_exiftool,
    _get_video_wh,
    _normalize_rotation,
    _apply_watermark_to_video,
    _get_video_rotation,
)

from media.motion_photo import (
    _RawMotionComponents,
    MotionPhotoSession,
    prepare_motion_photo,
    _split_motion_photo,
    _mp4_looks_valid,
    _find_mp4_start_by_ftyp,
)

__all__ = [
    # xmp
    "XMP_START_MARKER",
    "XMP_END_MARKER",
    "XMP_HEADER",
    "MICRO_VIDEO_OFFSET_PATTERN",
    "MICRO_VIDEO_LENGTH_PATTERN",
    "MOTIONPHOTO_FLAG_PATTERN",
    "OFFSET_ATTRS",
    "LENGTH_ATTRS",
    "_extract_xmp_segment",
    "_parse_first_match",
    "_looks_like_motionphoto_flag",
    "_update_container_directory_lengths",
    "_ensure_container_namespaces",
    "_detect_motion_video_mime",
    "_ensure_hdrgm_namespace_and_version",
    "_set_container_directory_ultrahdr_motion",
    "_prepare_xmp_ultrahdr_motion",
    "_prepare_xmp",
    "_update_attribute_if_exists",
    "_ensure_offset_length_attrs",
    "_strip_existing_xmp",
    "_build_xmp_segment",
    "_inject_xmp",
    # video
    "_copy_all_metadata_with_exiftool",
    "_get_video_wh",
    "_normalize_rotation",
    "_apply_watermark_to_video",
    "_get_video_rotation",
    # motion_photo
    "_RawMotionComponents",
    "MotionPhotoSession",
    "prepare_motion_photo",
    "_split_motion_photo",
    "_mp4_looks_valid",
    "_find_mp4_start_by_ftyp",
]
