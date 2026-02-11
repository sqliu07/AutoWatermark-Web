"""Application configuration management.

This module provides a centralized configuration management system using dataclasses
for type safety and validation. Configuration can be loaded from environment variables
for deployment flexibility.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class AppConfig:
    """Centralized application configuration.

    This class manages all application settings including paths, limits, rate limits,
    and feature flags. Configuration values can be overridden via environment variables.
    """

    # Project root - automatically resolved
    project_root: Path = field(init=False)

    # Path configurations
    upload_folder: Path = field(init=False)
    fonts_folder: Path = field(init=False)
    logos_folder: Path = field(init=False)
    config_folder: Path = field(init=False)
    static_folder: Path = field(init=False)
    i18n_folder: Path = field(init=False)

    # File upload limits
    max_content_length: int = 200 * 1024 * 1024  # 200MB
    max_image_pixels: int = 100_000_000
    allowed_extensions: Set[str] = field(default_factory=lambda: {"png", "jpg", "jpeg"})

    # Rate limiting
    default_rate_limits: List[str] = field(default_factory=lambda: ["2000 per day", "500 per hour"])
    upload_rate_limit: str = "10 per minute"
    zip_rate_limit: str = "10 per minute"

    # Cleanup intervals and retention
    task_retention_seconds: int = 3600  # 1 hour
    zip_retention_seconds: int = 3600  # 1 hour
    upload_retention_seconds: int = 86400  # 24 hours
    burn_ttl_seconds: int = 120  # 2 minutes
    cleaner_interval_seconds: int = 10

    # Executor configuration
    executor_max_workers: int = 4

    # Feature flags
    start_background_cleaner: bool = True

    # Image quality settings
    image_quality_map: Dict[str, int] = field(default_factory=lambda: {
        "high": 100,
        "medium": 85,
        "low": 75
    })

    # Font paths
    font_path_bold: Path = field(init=False)
    font_path_light: Path = field(init=False)

    # Watermark style config path
    watermark_style_config_path: Path = field(init=False)

    # Error messages (app-specific)
    error_messages: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "invalid_file_type": {
            "en": "Invalid file type! Please upload a PNG, JPG or JPEG file.",
            "zh": "无效的文件类型！请上传PNG、JPG或JPEG文件。"
        },
        "no_file_uploaded": {
            "en": "No file uploaded!",
            "zh": "未上传文件！"
        },
        "no_file_selected": {
            "en": "No file selected!",
            "zh": "未选择文件！"
        },
    })

    # Common error messages
    common_error_messages: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "unsupported_manufacturer": {
            "en": "Unsupported camera! Please wait for our update.",
            "zh": "暂不支持该品牌相机！请等待我们的更新。"
        },
        "no_exif_data": {
            "en": "This image does not contain valid exif data!",
            "zh": "该图片不包含有效的exif数据！"
        },
        "exif_read_error": {
            "en": "Failed to parse EXIF information from the image.",
            "zh": "无法从图片中解析 EXIF 信息。"
        },
        "unexpected_error": {
            "en": "An unexpected error occurred while processing the watermark.",
            "zh": "处理水印时发生未知错误。"
        },
        "image_too_large": {
            "en": "Image size exceeds 100 million pixels, too large to process!",
            "zh": "图片超过一亿像素，尺寸过大，无法处理！"
        },
    })

    # Camera brand aliases
    brand_aliases: Dict[str, str] = field(default_factory=lambda: {
        "sonycamera": "sony",
        "sonycorporation": "sony",
        "nikoncorporation": "nikon",
        "canoninc": "canon",
        "canoncamera": "canon",
        "fujifilmcorporation": "fujifilm",
        "fujifilmholdings": "fujifilm",
        "olympuscorporation": "olympus",
        "panasoniccorporation": "panasonic",
        "panasoniccorporationimaging": "panasonic",
        "leicacameraag": "leica",
        "pentaxricohimaging": "pentax",
        "xiaomi": "xiaomi",
        "apple": "apple",
        "oppo": "oppo"
    })

    # Image processing constants
    footer_ratio_landscape: float = 0.09
    footer_ratio_portrait: float = 0.08
    font_size_ratio: float = 0.22
    logo_height_ratio: float = 0.5
    portrait_font_scale: float = 0.75
    min_font_size: int = 20

    # Glass effect constants
    watermark_glass_bg_scale: float = 1.15
    watermark_glass_shadow_scale: float = 1.02
    watermark_glass_corner_radius_factor: float = 0.035
    watermark_glass_blur_radius: float = 0.025
    watermark_glass_color: int = 180
    watermark_glass_offset: float = 0.025
    watermark_glass_bg_threshold: int = 130

    def __post_init__(self):
        """Initialize path configurations and validate settings."""
        # Resolve project root
        self.project_root = Path(__file__).resolve().parent.parent

        # Initialize paths
        self.upload_folder = self.project_root / "upload"
        self.fonts_folder = self.project_root / "fonts"
        self.logos_folder = self.project_root / "logos"
        self.config_folder = self.project_root / "config"
        self.static_folder = self.project_root / "static"
        self.i18n_folder = self.static_folder / "i18n"

        # Initialize font paths
        self.font_path_bold = self.fonts_folder / "AlibabaPuHuiTi-2-85-Bold.otf"
        self.font_path_light = self.fonts_folder / "AlibabaPuHuiTi-2-45-Light.otf"

        # Initialize watermark style config path
        self.watermark_style_config_path = self.config_folder / "watermark_styles.toml"

        # Validate configuration
        self._validate()

    def _validate(self):
        """Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        if self.max_content_length <= 0:
            raise ValueError("max_content_length must be positive")
        if self.max_image_pixels <= 0:
            raise ValueError("max_image_pixels must be positive")
        if self.executor_max_workers <= 0:
            raise ValueError("executor_max_workers must be positive")
        if self.cleaner_interval_seconds <= 0:
            raise ValueError("cleaner_interval_seconds must be positive")
        if self.min_font_size < 1:
            raise ValueError("min_font_size must be >= 1")

        # Validate ratios
        if not (0 < self.footer_ratio_landscape < 1):
            raise ValueError("footer_ratio_landscape must be between 0 and 1")
        if not (0 < self.footer_ratio_portrait < 1):
            raise ValueError("footer_ratio_portrait must be between 0 and 1")
        if not (0 < self.font_size_ratio < 1):
            raise ValueError("font_size_ratio must be between 0 and 1")
        if not (0 < self.logo_height_ratio < 1):
            raise ValueError("logo_height_ratio must be between 0 and 1")

        # Validate retention times
        if self.task_retention_seconds <= 0:
            raise ValueError("task_retention_seconds must be positive")
        if self.zip_retention_seconds <= 0:
            raise ValueError("zip_retention_seconds must be positive")
        if self.upload_retention_seconds <= 0:
            raise ValueError("upload_retention_seconds must be positive")
        if self.burn_ttl_seconds <= 0:
            raise ValueError("burn_ttl_seconds must be positive")

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create configuration from environment variables.

        Environment variables can override default values:
        - MAX_CONTENT_LENGTH: Maximum upload size in bytes
        - MAX_IMAGE_PIXELS: Maximum image pixels
        - UPLOAD_FOLDER: Path to upload directory
        - EXECUTOR_MAX_WORKERS: Number of worker threads
        - CLEANER_INTERVAL_SECONDS: Cleanup interval
        - START_BACKGROUND_CLEANER: Enable/disable background cleaner (true/false)

        Returns:
            AppConfig: Configuration instance with environment overrides applied.
        """
        config = cls()

        # Override with environment variables if present
        if env_max := os.getenv("MAX_CONTENT_LENGTH"):
            config.max_content_length = int(env_max)

        if env_pixels := os.getenv("MAX_IMAGE_PIXELS"):
            config.max_image_pixels = int(env_pixels)

        if env_upload := os.getenv("UPLOAD_FOLDER"):
            config.upload_folder = Path(env_upload)

        if env_workers := os.getenv("EXECUTOR_MAX_WORKERS"):
            config.executor_max_workers = int(env_workers)

        if env_interval := os.getenv("CLEANER_INTERVAL_SECONDS"):
            config.cleaner_interval_seconds = int(env_interval)

        if env_cleaner := os.getenv("START_BACKGROUND_CLEANER"):
            config.start_background_cleaner = env_cleaner.lower() in ("true", "1", "yes")

        # Re-validate after overrides
        config._validate()

        return config

    def get_error_message(self, key: str, lang: str = "zh", category: str = "app") -> Optional[str]:
        """Get localized error message.

        Args:
            key: Error message key.
            lang: Language code (zh or en).
            category: Message category (app or common).

        Returns:
            Localized error message or None if not found.
        """
        messages = self.error_messages if category == "app" else self.common_error_messages
        return messages.get(key, {}).get(lang)

    def get_image_quality(self, quality: str) -> int:
        """Get image quality value.

        Args:
            quality: Quality level (high, medium, low).

        Returns:
            Quality value (0-100).
        """
        return self.image_quality_map.get(quality, 100)

    def normalize_brand(self, manufacturer: str) -> Optional[str]:
        """Normalize camera brand name using aliases.

        Args:
            manufacturer: Raw manufacturer name from EXIF.

        Returns:
            Normalized brand name or None if not found.
        """
        normalized = manufacturer.lower().replace(" ", "").replace("-", "")
        return self.brand_aliases.get(normalized)
