"""T03：seed_admin CLI 幂等（09 §2-T03 / 04 §8）。密码走 stdin（monkeypatch）。"""
from sqlalchemy import select

import app.seed_admin as seed
from app.db.models import User


def _stdin(monkeypatch, line: str):
    class _Stdin:
        def isatty(self):
            return False

        def readline(self):
            return line

    monkeypatch.setattr(seed.sys, "stdin", _Stdin())


def test_seed_creates_admin(db, monkeypatch):
    _stdin(monkeypatch, "adm1nPass\n")
    rc = seed.main(["--username", "boss", "--email", "boss@local"])
    assert rc == seed.EXIT_OK
    u = db.execute(select(User).where(User.username == "boss")).scalar_one()
    assert u.is_admin is True
    assert u.is_active is True


def test_seed_idempotent(db, monkeypatch):
    _stdin(monkeypatch, "adm1nPass\n")
    assert seed.main(["--username", "boss", "--email", "boss@local"]) == seed.EXIT_OK
    # 同 username / 同 email 再跑 → EXIT_EXISTS（对齐 409 语义）
    assert seed.main(["--username", "boss", "--email", "boss@local"]) == seed.EXIT_EXISTS
    assert seed.main(["--username", "boss2", "--email", "boss@local"]) == seed.EXIT_EXISTS
    # 只有一条
    assert len(db.execute(select(User).where(User.is_admin.is_(True))).scalars().all()) == 1


def test_seed_short_password_rejected(db, monkeypatch):
    _stdin(monkeypatch, "short1\n")
    rc = seed.main(["--username", "boss", "--email", "boss@local"])
    assert rc == seed.EXIT_ERROR
    assert db.execute(select(User.id).where(User.username == "boss")).first() is None
