class CommonConstants:
    UPLOAD_FOLDER = './upload'

    IMAGE_QUALITY_MAP = {
        "high": 100,
        "medium": 85,
        "low": 75
    }

    GLOBAL_FONT_PATH_BOLD = "./fonts/AlibabaPuHuiTi-2-85-Bold.otf"
    GLOBAL_FONT_PATH_LIGHT = "./fonts/AlibabaPuHuiTi-2-45-Light.otf"

    ERROR_MESSAGES = {
        "unsupported_manufacturer": {
            'en': "Unsupported camera! Please wait for our update.",
            'zh': "暂不支持该品牌相机！请等待我们的更新。"
        },
        "no_exif_data": {
            'en': "This image does not contain valid exif data!",
            'zh': "该图片不包含有效的exif数据！"
        },
        "exif_read_error": {
            'en': "Failed to parse EXIF information from the image.",
            'zh': "无法从图片中解析 EXIF 信息。"
        },
        "unexpected_error": {
            'en': "An unexpected error occurred while processing the watermark.",
            'zh': "处理水印时发生未知错误。"
        },
    }
    
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
    "xiaomi":  "xiaomi",
    "apple": "apple",
    "oppo": "oppo"
}

class AppConstants:
    UPLOAD_FOLDER = './upload'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 最大文件 200MB

    DEFAULT_RATE_LIMITS = ["2000 per day", "500 per hour"]
    UPLOAD_RATE_LIMIT = "10 per minute"
    ZIP_RATE_LIMIT = "10 per minute"

    EXECUTOR_MAX_WORKERS = 4
    TASK_RETENTION_SECONDS = 3600

    CLEANER_INTERVAL_SECONDS = 10
    BURN_TTL_SECONDS = 120
    ZIP_RETENTION_SECONDS = 3600
    UPLOAD_RETENTION_SECONDS = 86400

    ERROR_MESSAGES = {
        "invalid_file_type": {
            'en': "Invalid file type! Please upload a PNG, JPG or JPEG file.",
            'zh': "无效的文件类型！请上传PNG、JPG或JPEG文件。"
        },
        "no_file_uploaded": {
            'en': "No file uploaded!",
            'zh': "未上传文件！"
        },
        "no_file_selected": {
            'en': "No file selected!",
            'zh': "未选择文件！"
        },
    }


class ImageConstants:
    # 底栏高度占图片高度的比例
    FOOTER_RATIO_LANDSCAPE = 0.09  # 横图 9%
    FOOTER_RATIO_PORTRAIT = 0.08   # 竖图 8%

    # 关键：字号占底栏高度的比例
    FONT_SIZE_RATIO = 0.22 

    # Logo 高度占底栏高度的比例
    LOGO_HEIGHT_RATIO = 0.5

    WATERMARK_GLASS_BG_SCALE = 1.15
    WATERMARK_GLASS_SHADOW_SCALE = 1.02
    WATERMARK_GLASS_CORNER_RADIUS_FACTOR = 0.035
    WATERMARK_GLASS_BLUR_RADIUS = 0.025
    WATERMARK_GLASS_COLOR = 180
    WATERMARK_GLASS_OFFSET = 0.025
    WATERMARK_GLASS_BG_THRESHOLD = 130