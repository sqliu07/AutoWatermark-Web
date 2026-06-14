"""下载链接签名：HMAC + 过期时间戳，防止链接被随意分享。"""

import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

DEFAULT_TTL = 3600  # 1 小时
_SECRET_PLACEHOLDER = "__CHANGE_ME__"


def _get_secret() -> str:
    secret = os.environ.get("DOWNLOAD_TOKEN_SECRET", "").strip()
    return secret


def ensure_secret_configured() -> None:
    secret = _get_secret()
    if not secret or secret == _SECRET_PLACEHOLDER:
        raise RuntimeError("DOWNLOAD_TOKEN_SECRET must be set to a non-placeholder value")


def _canonical_claims(claims: dict) -> str:
    return "&".join(f"{key}={claims[key]}" for key in sorted(claims))


def _token_payload(filename: str, expires: int, claims: dict) -> str:
    canonical_claims = _canonical_claims({k: str(v) for k, v in claims.items() if v is not None})
    return f"{filename}:{expires}:{canonical_claims}"


def generate_token(filename: str, ttl: int = DEFAULT_TTL, **claims) -> tuple[str, int]:
    """生成带过期时间的签名 token。返回 (token, expires)。"""
    secret = _get_secret()
    if not secret or secret == _SECRET_PLACEHOLDER:
        raise RuntimeError("DOWNLOAD_TOKEN_SECRET is not configured")
    expires = int(time.time()) + ttl
    payload = _token_payload(filename, expires, claims)
    token = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return token, expires


def verify_token(filename: str, token: str, expires: str, **claims) -> bool:
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

    payload = _token_payload(filename, expires_int, claims)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(token, expected)


def build_signed_url(path: str, filename: str, **extra_params) -> str:
    """构建带签名的下载 URL。"""
    token, expires = generate_token(filename, **extra_params)
    params = {**extra_params, "token": token, "expires": str(expires)}
    query = urlencode(params)
    return f"{path}?{query}"
