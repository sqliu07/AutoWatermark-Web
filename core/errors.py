class WatermarkError(Exception):
    """Base class for predictable watermark processing errors."""

    def __init__(self, message_key, detail=None):
        super().__init__(message_key)
        self.message_key = message_key
        self.detail = detail

    def get_message_key(self):
        return self.message_key

    def get_detail(self):
        return self.detail


class MissingExifDataError(WatermarkError):
    def __init__(self, detail=None):
        super().__init__("no_exif_data", detail=detail)


class UnsupportedManufacturerError(WatermarkError):
    def __init__(self, manufacturer, detail=None):
        super().__init__("unsupported_manufacturer", detail=detail or manufacturer)
        self.manufacturer = manufacturer


class ExifProcessingError(WatermarkError):
    def __init__(self, detail=None):
        super().__init__("exif_read_error", detail=detail)


class UnexpectedProcessingError(WatermarkError):
    def __init__(self, detail=None):
        super().__init__("unexpected_error", detail=detail)


class ImageTooLargeError(WatermarkError):
    def __init__(self, detail=None):
        super().__init__("image_too_large", detail=detail)
