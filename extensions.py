from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config.settings import AppConfig

config = AppConfig()
limiter = Limiter(
    get_remote_address,
    default_limits=config.default_rate_limits,
    storage_uri="memory://",
)
