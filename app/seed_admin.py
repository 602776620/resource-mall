"""管理端种子 CLI（04 §8）。

用法：
    python -m app.seed_admin --username admin --email admin@local --password <从 stdin 读取>

幂等：已存在（同 username 或 email）→ 提示退出码 1（对齐 409 语义）。
is_admin 仅由 seed / 后台 toggle 产生（06 §1 红线 4，无注册自提权路径）。
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core import security
from app.db.base import SessionLocal
from app.db.models import User

EXIT_OK = 0
EXIT_EXISTS = 1
EXIT_ERROR = 2


def _read_password(explicit: str | None) -> str:
    if explicit:
        return explicit
    # 04 §8：密码从 stdin 读取。
    # - stdin 为管道（自动化 / `echo pw | seed_admin`）→ 直接读一行，可自动化。
    # - 交互终端 → getpass 隐藏输入（不回显）。
    if not sys.stdin.isatty():
        return sys.stdin.readline().strip()
    return getpass.getpass("admin password (hidden): ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed an admin user (idempotent).")
    parser.add_argument("--username", required=True, help="admin username")
    parser.add_argument("--email", required=True, help="admin email")
    parser.add_argument(
        "--password",
        default=None,
        help="admin password (default: read from stdin, hidden)",
    )
    args = parser.parse_args(argv)

    password = _read_password(args.password)
    username = args.username.strip()
    email = args.email.strip().lower()

    if len(password) < 8:
        print("error: password too short (min 8 chars)", file=sys.stderr)
        return EXIT_ERROR

    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where((User.username == username) | (User.email == email))
        ).scalars().first()
        if existing is not None:
            print(f"admin already exists (id={existing.id}); no-op", file=sys.stderr)
            return EXIT_EXISTS

        user = User(
            username=username,
            email=email,
            password_hash=security.hash_password(password),
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"admin created: id={user.id} username={username}")
        return EXIT_OK
    except Exception as e:  # noqa: BLE001 - CLI 兜底，避免裸栈
        db.rollback()
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
