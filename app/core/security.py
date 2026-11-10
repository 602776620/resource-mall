"""认证与签名原语（06 §4）：argon2id 密码哈希、JWT 签发/校验、refresh 令牌哈希。

红线：
- JWT payload 只放 sub / exp / jti，不放 is_admin（每次从 DB 读，防权限缓存）。
- refresh 令牌为不透明随机串，库内只存 SHA-256 hex（原文不落库）。
- access 15min / refresh 7d（settings 控制）。
"""
import hashlib
import secrets
import time
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type

from app.core.config import settings

# argon2id 参数（06 §4）：m=64MB(=65536 KiB), t=3, p=4
_PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, type=Type.ID)

_JWT_ALG = "HS256"


def hash_password(plain: str) -> str:
    return _PH.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _PH.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    """参数升级后判断是否需重哈希（登录成功时顺带更新）。"""
    try:
        return _PH.check_needs_rehash(hashed)
    except Exception:  # noqa: BLE001 - 旧哈希解析失败按需重哈希
        return True


def create_access_token(user_id: int, *, jti: str | None = None) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": jti or uuid.uuid4().hex,
        "iat": now,
        "exp": now + settings.jwt_access_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并校验（过期/签名错抛 jwt.PyJWTError）。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALG])


def create_refresh_token() -> tuple[str, str]:
    """返回 (原文, sha256_hex)。原文下发给客户端，hash 存库。"""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_ttl_seconds() -> int:
    return settings.jwt_refresh_days * 86400
