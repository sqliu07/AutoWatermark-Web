from pathlib import Path

_ROOT = Path(__file__).resolve().parent


class CommonConstants:
    WATERMARK_STYLE_CONFIG_PATH = str(_ROOT / "config" / "watermark_styles.toml")
    ERROR_MESSAGES_PATH = str(_ROOT / "config" / "error_messages.json")

    IMAGE_QUALITY_MAP = {
        "high": 100,
        "medium": 85,
        "low": 75
    }

    GLOBAL_FONT_PATH_BOLD = str(_ROOT / "fonts" / "AlibabaPuHuiTi-2-85-Bold.otf")
    GLOBAL_FONT_PATH_REGULAR = str(_ROOT / "fonts" / "AlibabaPuHuiTi-2-55-Regular.otf")
    GLOBAL_FONT_PATH_LIGHT = str(_ROOT / "fonts" / "AlibabaPuHuiTi-2-45-Light.otf")
    GLOBAL_FONT_PATH_MONO = str(_ROOT / "fonts" / "RobotoMono-Regular.ttf")

    BRAND_ALIASES = {
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
        "oppo": "oppo",
    }

class AppConstants:
    UPLOAD_FOLDER = str(_ROOT / "upload")
    STATE_DB_FILENAME = "app_state.sqlite3"
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 最大文件 200MB

    DEFAULT_RATE_LIMITS = ["2000 per day", "500 per hour"]
    UPLOAD_RATE_LIMIT = "10 per minute"
    ZIP_RATE_LIMIT = "10 per minute"
    ZIP_MAX_FILES = 50

    EXECUTOR_MAX_WORKERS = 4
    TASK_RETENTION_SECONDS = 3600

    CLEANER_INTERVAL_SECONDS = 10
    BURN_TTL_SECONDS = 120
    ZIP_RETENTION_SECONDS = 3600
    UPLOAD_RETENTION_SECONDS = 86400



def format_pixel_limit(limit: int, lang: str = "zh") -> str:
    if lang == "en":
        if limit >= 1_000_000 and limit % 1_000_000 == 0:
            return f"{limit // 1_000_000} million"
        return f"{limit:,}"
    if limit >= 100_000_000 and limit % 100_000_000 == 0:
        return f"{limit // 100_000_000}亿"
    if limit >= 10_000 and limit % 10_000 == 0:
        return f"{limit // 10_000}万"
    return str(limit)


class ImageConstants:
    MAX_IMAGE_PIXELS = 200_000_000

    # split_lr 布局中右侧 Logo 高度占底栏的比例
    LOGO_HEIGHT_RATIO = 0.5

    WATERMARK_GLASS_BG_SCALE = 1.15
    WATERMARK_GLASS_SHADOW_SCALE = 1.02
    WATERMARK_GLASS_CORNER_RADIUS_FACTOR = 0.035
    WATERMARK_GLASS_BLUR_RADIUS = 0.025
    WATERMARK_GLASS_COLOR = 180
    WATERMARK_GLASS_OFFSET = 0.025
    WATERMARK_GLASS_BG_THRESHOLD = 130
