"""下载链接签名：HMAC + 过期时间戳，防止链接被随意分享。"""

import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

DEFAULT_TTL = 3600  # 1 小时


def _get_secret() -> str:
    secret = os.environ.get("DOWNLOAD_TOKEN_SECRET", "").strip()
    return secret


def ensure_secret_configured() -> None:
    if not _get_secret():
        raise RuntimeError("DOWNLOAD_TOKEN_SECRET is required in production and testing environments")


def generate_token(filename: str, ttl: int = DEFAULT_TTL) -> tuple[str, int]:
    """生成带过期时间的签名 token。返回 (token, expires)。"""
    secret = _get_secret()
    if not secret:
        raise RuntimeError("DOWNLOAD_TOKEN_SECRET is not configured")
    expires = int(time.time()) + ttl
    payload = f"{filename}:{expires}"
    token = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return token, expires


def verify_token(filename: str, token: str, expires: str) -> bool:
    """校验 token 是否有效且未过期。"""
    secret = _get_secret()
    if not secret:
        return False
    try:
        expires_int = int(expires)
    except (ValueError, TypeError):
        return False

    if time.time() > expires_int:
        return False

    payload = f"{filename}:{expires_int}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(token, expected)


def build_signed_url(path: str, filename: str, **extra_params) -> str:
    """构建带签名的下载 URL。"""
    token, expires = generate_token(filename)
    params = {**extra_params, "token": token, "expires": str(expires)}
    query = urlencode(params)
    return f"{path}?{query}"
