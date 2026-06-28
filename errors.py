from enum import Enum


def _image_too_large_kwargs(lang: str) -> dict:
    from constants import ImageConstants, format_pixel_limit
    return {"limit": format_pixel_limit(ImageConstants.MAX_IMAGE_PIXELS, lang)}


class WatermarkErrorCode(Enum):
    MISSING_EXIF_DATA = ("no_exif_data", 400)
    UNSUPPORTED_MANUFACTURER = ("unsupported_manufacturer", 400)
    EXIF_PROCESSING_ERROR = ("exif_read_error", 422)
    UNEXPECTED_ERROR = ("unexpected_error", 500)
    IMAGE_TOO_LARGE = ("image_too_large", 413, _image_too_large_kwargs)

    @property
    def message_key(self) -> str:
        return self.value[0]

    @property
    def http_status(self) -> int:
        return self.value[1]

    def get_message_kwargs(self, lang: str = "zh") -> dict:
        if len(self.value) > 2 and callable(self.value[2]):
            return self.value[2](lang)
        return {}


class WatermarkError(Exception):
    """Predictable watermark processing errors identified by a WatermarkErrorCode."""

    def __init__(self, error_code: WatermarkErrorCode, detail: str | None = None, **message_kwargs):
        super().__init__(error_code.message_key)
        self.error_code = error_code
        self.detail = detail
        self._message_kwargs = message_kwargs

    @property
    def message_key(self) -> str:
        return self.error_code.message_key

    @property
    def http_status(self) -> int:
        return self.error_code.http_status

    def get_message_kwargs(self, lang: str = "zh") -> dict:
        kwargs = dict(self.error_code.get_message_kwargs(lang))
        kwargs.update(self._message_kwargs)
        return kwargs
