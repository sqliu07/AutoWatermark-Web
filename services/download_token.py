"""下载链接签名：HMAC + 过期时间戳，防止链接被随意分享。"""

import hashlib
import hmac
import os
import time

_SECRET = os.environ.get("DOWNLOAD_TOKEN_SECRET", "")
if not _SECRET:
    import warnings
    warnings.warn(
        "DOWNLOAD_TOKEN_SECRET not set; using random secret (tokens will invalidate on restart)",
        stacklevel=1,
    )
    import secrets
    _SECRET = secrets.token_hex(32)
DEFAULT_TTL = 3600  # 1 小时


def generate_token(filename: str, ttl: int = DEFAULT_TTL) -> tuple[str, int]:
    """生成带过期时间的签名 token。返回 (token, expires)。"""
    expires = int(time.time()) + ttl
    payload = f"{filename}:{expires}"
    token = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return token, expires


def verify_token(filename: str, token: str, expires: str) -> bool:
    """校验 token 是否有效且未过期。"""
    try:
        expires_int = int(expires)
    except (ValueError, TypeError):
        return False

    if time.time() > expires_int:
        return False

    payload = f"{filename}:{expires_int}"
    expected = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(token, expected)


def build_signed_url(path: str, filename: str, **extra_params) -> str:
    """构建带签名的下载 URL。"""
    token, expires = generate_token(filename)
    params = {**extra_params, "token": token, "expires": str(expires)}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{path}?{query}"
