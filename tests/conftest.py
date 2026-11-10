"""pytest 基座（09 §2）。

- 测试进程强制 DB 指向独立库 `mall_test`（与开发库 mall 隔离，pydantic-settings 中
  环境变量优先于 .env 文件）。Redis 对认证无关，按需打桩。
- 提供 `db` 会话 fixture：建表（create_all）+ 每测试前清空 users/refresh_tokens 保证隔离。
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在任何 app 模块导入前设置（settings 在首次访问时 lru_cache）。
# mall 用户拥有 mall_test 库；密码与 .env 一致（测试环境）。
os.environ["DB_DSN"] = (
    os.environ.get("TEST_DB_DSN", "")
    or "postgresql+psycopg://mall:25c20ed203f3722e42561cd10b2706d4@127.0.0.1:5432/mall_test"
)


@pytest.fixture(autouse=True, scope="session")
def _ensure_schema():
    from app.db.base import Base, engine
    from app.db import models  # noqa: F401 - 注册全部模型

    Base.metadata.create_all(engine)
    yield
    # 不清库结构，保留迁移产物供复用。


@pytest.fixture()
def db():
    """独立会话，每测试前清空认证相关表，保证用例隔离。"""
    from sqlalchemy import text

    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        with session.begin():
            session.execute(text("TRUNCATE refresh_tokens, users RESTART IDENTITY CASCADE"))
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture()
def client(db):  # noqa: F841 - db fixture 保证清表；client 挂 .session 供 helper 建数据
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.session = db  # 测试侧数据准备入口（与 app 同库同会话池）
        yield c
