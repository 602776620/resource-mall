"""依赖注入：DB / Redis 会话（07 §1，认证类依赖 T03 补）。"""
from collections.abc import Iterator

import redis as redis_lib
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import SessionLocal

_redis: "redis_lib.Redis | None" = None


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
