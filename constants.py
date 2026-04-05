class CommonConstants:
    WATERMARK_STYLE_CONFIG_PATH = "./config/watermark_styles.toml"

    IMAGE_QUALITY_MAP = {
        "high": 100,
        "medium": 85,
        "low": 75
    }

    GLOBAL_FONT_PATH_BOLD = "./fonts/AlibabaPuHuiTi-2-85-Bold.otf"
    GLOBAL_FONT_PATH_REGULAR = "./fonts/AlibabaPuHuiTi-2-55-Regular.otf"
    GLOBAL_FONT_PATH_LIGHT = "./fonts/AlibabaPuHuiTi-2-45-Light.otf"
    GLOBAL_FONT_PATH_MONO = "./fonts/RobotoMono-Regular.ttf"

    ERROR_MESSAGES = {
        # 图像处理类
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
        "image_too_large": {
            'en': "Image size exceeds 100 million pixels, too large to process!",
            'zh': "图片超过一亿像素，尺寸过大，无法处理！"
        },
        # 上传校验类
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
        # HTTP 错误
        "rate_limit_exceeded": {
            'en': "Too many requests, please try again later.",
            'zh': "请求过于频繁，请稍后再试。"
        },
        "file_not_found": {
            'en': "File not found.",
            'zh': "文件不存在。"
        },
        "link_expired": {
            'en': "Link expired or invalid.",
            'zh': "链接已过期或无效。"
        },
        "zip_too_many_files": {
            'en': "Too many files.",
            'zh': "文件数量过多。"
        },
        "zip_no_files": {
            'en': "No files provided.",
            'zh': "未提供文件。"
        },
        "zip_create_failed": {
            'en': "Failed to create zip.",
            'zh': "创建压缩包失败。"
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
        "xiaomi": "xiaomi",
        "apple": "apple",
        "oppo": "oppo",
    }

class AppConstants:
    UPLOAD_FOLDER = './upload'
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



class ImageConstants:
    MAX_IMAGE_PIXELS = 100_000_000

    # split_lr 布局中右侧 Logo 高度占底栏的比例
    LOGO_HEIGHT_RATIO = 0.5

    WATERMARK_GLASS_BG_SCALE = 1.15
    WATERMARK_GLASS_SHADOW_SCALE = 1.02
    WATERMARK_GLASS_CORNER_RADIUS_FACTOR = 0.035
    WATERMARK_GLASS_BLUR_RADIUS = 0.025
    WATERMARK_GLASS_COLOR = 180
    WATERMARK_GLASS_OFFSET = 0.025
    WATERMARK_GLASS_BG_THRESHOLD = 130
