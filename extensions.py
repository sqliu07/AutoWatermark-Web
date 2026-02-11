from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from constants import AppConstants

limiter = Limiter(
    get_remote_address,
    default_limits=AppConstants.DEFAULT_RATE_LIMITS,
    storage_uri="memory://",
)
