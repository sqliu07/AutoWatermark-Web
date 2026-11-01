"""Bounds applied before raster allocation, including metadata-derived text sizes.

These are per-image limits; the executor must also bound concurrent tasks.
"""
from PIL import Image

from constants import ImageConstants
from errors import WatermarkError, WatermarkErrorCode

MAX_RASTER_PIXELS = 40_000_000
MAX_INPUT_EDGE = 16384
MAX_INPUT_ASPECT = 32


def validate_raster_size(size):
    width, height = size
    limit = min(ImageConstants.MAX_IMAGE_PIXELS or MAX_RASTER_PIXELS, MAX_RASTER_PIXELS)
    if width <= 0 or height <= 0 or width * height > limit:
        raise WatermarkError(WatermarkErrorCode.IMAGE_TOO_LARGE, detail=f'{width}x{height}')


def validate_input_size(size):
    validate_raster_size(size)
    width, height = size
    if max(size) > MAX_INPUT_EDGE or max(size) > min(size) * MAX_INPUT_ASPECT:
        raise WatermarkError(WatermarkErrorCode.IMAGE_TOO_LARGE, detail=f'{width}x{height}')


def new_image(mode, size, color=0):
    validate_raster_size(size)
    return Image.new(mode, size, color)
