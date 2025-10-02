class CommonConstants:
    #for app.py
    UPLOAD_FOLDER = './upload'

    #for process.py
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

class ImageConstants:
    #for image_utils.py
    ORIGIN_BOTTOM_BORDER_RATIO = 0.08
    ORIGIN_TOP_BORDER_RATIO = 0.03
    LOGO_RATIO = 0.07
    ORIGIN_BOTTOM_HEIGHT = 250
