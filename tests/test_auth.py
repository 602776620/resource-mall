"""T03 认证（09 §2-T03）。打真实测试库 mall_test，逐条验收。"""
from datetime import datetime, timedelta, timezone

from app.core import security
from app.db.models import RefreshToken, User

# ---- 辅助 ----


def _sess(target):
    """兼容 TestClient（挂 .session）与裸 Session 两种入参。"""
    return target.session if hasattr(target, "session") else target


def _mk_user(target, *, username="alice", email="alice@x.com", admin=False, active=True,
             password="passw0rd"):
    db = _sess(target)
    u = User(
        username=username,
        email=email,
        password_hash=security.hash_password(password),
        is_admin=admin,
        is_active=active,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_refresh(target, user: User, *, revoked=False, expired=False) -> str:
    db = _sess(target)
    raw, h = security.create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=h,
            expires_at=datetime.now(timezone.utc)
            + (timedelta(days=-1) if expired else timedelta(days=7)),
            revoked_at=datetime.now(timezone.utc) if revoked else None,
        )
    )
    db.commit()
    return raw


# ---- 注册 ----


def test_register_with_username(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "passw0rd", "password_confirm": "passw0rd"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "bob"
    assert body["user"]["is_admin"] is False  # 注册不可提权（04 §8）
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["expires_in"] == 15 * 60


def test_register_email_only(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "carol@x.com", "password": "passw0rd", "password_confirm": "passw0rd"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "carol@x.com"
    assert r.json()["user"]["username"] is None


def test_register_requires_one_of_username_or_email(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"password": "passw0rd", "password_confirm": "passw0rd"},
    )
    assert r.status_code == 422


def test_register_duplicate_username_409(client):
    _mk_user(client, username="dup")
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "dup", "password": "passw0rd", "password_confirm": "passw0rd"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_register_duplicate_email_409(client):
    _mk_user(client, email="dup@x.com")
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "DUP@x.com", "password": "passw0rd", "password_confirm": "passw0rd"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_register_weak_password_422(client):
    # 纯字母无数字
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "weak1", "password": "abcdefgh", "password_confirm": "abcdefgh"},
    )
    assert r.status_code == 422
    # 纯数字无字母
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "weak2", "password": "12345678", "password_confirm": "12345678"},
    )
    assert r.status_code == 422
    # 过短
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "weak3", "password": "a1", "password_confirm": "a1"},
    )
    assert r.status_code == 422


def test_register_password_mismatch_422(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "mm", "password": "passw0rd", "password_confirm": "diff0rent"},
    )
    assert r.status_code == 422


def test_register_email_lowercased(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "MIX@X.com", "password": "passw0rd", "password_confirm": "passw0rd"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "mix@x.com"


# ---- 登录 ----


def test_login_by_username(client):
    _mk_user(client, username="alice", password="passw0rd")
    r = client.post("/api/v1/auth/login", json={"account": "alice", "password": "passw0rd"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["username"] == "alice"


def test_login_by_email(client):
    _mk_user(client, email="alice@x.com", password="passw0rd")
    r = client.post(
        "/api/v1/auth/login", json={"account": "alice@x.com", "password": "passw0rd"}
    )
    assert r.status_code == 200


def test_login_wrong_password_bad_credentials(client):
    _mk_user(client, username="alice", password="passw0rd")
    r = client.post("/api/v1/auth/login", json={"account": "alice", "password": "wrong000"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "BAD_CREDENTIALS"


def test_login_unknown_user_same_code(client):
    # 防枚举：用户不存在 与 密码错 同一 code
    r = client.post("/api/v1/auth/login", json={"account": "ghost", "password": "wrong000"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "BAD_CREDENTIALS"


def test_login_disabled_user_403(client):
    _mk_user(client, username="banned", password="passw0rd", active=False)
    r = client.post("/api/v1/auth/login", json={"account": "banned", "password": "passw0rd"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


# ---- refresh 轮换 ----


def test_refresh_rotates_and_old_is_invalid(client, db):
    u = _mk_user(db, username="alice")
    old_raw = _mk_refresh(db, u)

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": old_raw})
    assert r.status_code == 200, r.text
    new_raw = r.json()["refresh_token"]
    assert new_raw != old_raw
    assert r.json()["access_token"]

    # 旧 refresh 复用 → 401 REFRESH_INVALID（03 铁律防重放）
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_raw})
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "REFRESH_INVALID"


def test_refresh_unknown_token_401(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "REFRESH_INVALID"


def test_refresh_expired_token_401(client, db):
    u = _mk_user(db, username="alice")
    raw = _mk_refresh(db, u, expired=True)
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 401


# ---- /users/me 与守卫 ----


def test_me_requires_token(client):
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_returns_current_user(client, db):
    u = _mk_user(db, username="alice", admin=False)
    access = security.create_access_token(u.id)
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "alice"
    assert r.json()["is_admin"] is False


def test_me_garbage_token_401(client):
    r = client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbag3"})
    assert r.status_code == 401


def test_me_disabled_user_403(client, db):
    u = _mk_user(db, username="banned", active=False)
    access = security.create_access_token(u.id)
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_require_admin_blocks_non_admin(client):
    # /admin/* 尚未挂路由；直接验证 require_admin 依赖行为（非管理员 → 403）
    from fastapi import APIRouter, Depends
    from app.main import app
    from app.core.deps import require_admin

    rtr = APIRouter()

    @rtr.get("/probe")
    def probe(admin=Depends(require_admin)):
        return {"admin": admin.username}

    app.include_router(rtr, prefix="/api/v1/_probe")
    u = _mk_user(client, username="alice", admin=False)
    access = security.create_access_token(u.id)
    resp = client.get("/api/v1/_probe/probe", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 403
    # 清理探针路由
    app.routes[:] = [rt for rt in app.routes if getattr(rt, "path", "") != "/api/v1/_probe/probe"]


# ---- 改密踢下线 ----


def test_change_password_kicks_offline(client, db):
    u = _mk_user(db, username="alice", password="passw0rd")
    old_raw = _mk_refresh(db, u)
    access = security.create_access_token(u.id)

    r = client.put(
        "/api/v1/users/me/password",
        json={"old_password": "passw0rd", "new_password": "newpass1"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text

    # 旧 refresh 全部吊销 → 无法换新 token
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_raw})
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "REFRESH_INVALID"

    # 能用新密码登录
    r3 = client.post(
        "/api/v1/auth/login", json={"account": "alice", "password": "newpass1"}
    )
    assert r3.status_code == 200


def test_change_password_wrong_old_422(client, db):
    u = _mk_user(db, username="alice", password="passw0rd")
    access = security.create_access_token(u.id)
    r = client.put(
        "/api/v1/users/me/password",
        json={"old_password": "wrong000", "new_password": "newpass1"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 422


# ---- 登出（幂等）----


def test_logout_revokes_then_idempotent(client, db):
    u = _mk_user(db, username="alice")
    raw = _mk_refresh(db, u)
    access = security.create_access_token(u.id)

    r1 = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": raw},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r1.status_code == 200
    # 已被吊销的 refresh 再用 → 401
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert r2.status_code == 401


def test_logout_idempotent_unknown_token(client, db):
    u = _mk_user(db, username="alice")
    access = security.create_access_token(u.id)
    r = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "unknown"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200  # 幂等：不报错
