"""依赖注入：DB / Redis 会话 + 认证（07 §1，T03 补认证）。"""
from collections.abc import Iterator

import jwt as pyjwt
import redis as redis_lib
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BizError
from app.core.security import decode_access_token
from app.db.base import SessionLocal
from app.db.models import User

_redis: "redis_lib.Redis | None" = None

# auto_error=False：缺 Authorization 头时不直接 403，交由 handler 统一转 401 UNAUTHENTICATED
_bearer = HTTPBearer(auto_error=False)


def get_redis() -> "redis_lib.Redis":
    global _redis
    if _redis is None:
        _redis = redis_lib.Redis.from_url(
            settings.redis_dsn,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer access token → 当前用户。未带/无效/过期 → 401 UNAUTHENTICATED。

    06 §4：payload 只有 sub，权限（is_active/is_admin）每次从 DB 读，不信任 JWT 内缓存。
    """
    if creds is None or not creds.credentials:
        raise BizError("未认证", status=401, code="UNAUTHENTICATED")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError):
        raise BizError("未认证", status=401, code="UNAUTHENTICATED")

    user = db.get(User, user_id)
    if user is None:
        raise BizError("未认证", status=401, code="UNAUTHENTICATED")
    if not user.is_active:
        # 06 §1：禁用用户访问受保护资源 → 403（区别于未认证的 401）
        raise BizError("用户已禁用", status=403, code="FORBIDDEN")
    return user


def require_admin(current: User = Depends(get_current_user)) -> User:
    """管理员守卫（06 §1 红线 1）：非管理员 → 403。须在 get_current_user 之后。"""
    if not current.is_admin:
        raise BizError("需要管理员权限", status=403, code="FORBIDDEN")
    return current
