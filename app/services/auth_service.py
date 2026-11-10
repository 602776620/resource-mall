"""认证业务逻辑（04 §3 / 06 §4）。依赖注入 db，可单测。

错误一律抛 BizError（07 §3.5）→ 全局 handler 转 04 错误体。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.core import security
from app.core.config import settings
from app.db.models import RefreshToken, User
from app.schemas.auth import (
    AuthResult,
    ChangePasswordIn,
    LoginIn,
    RefreshIn,
    RefreshOut,
    RegisterIn,
    TokensOut,
    UserOut,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _issue_tokens(db: Session, user: User) -> TokensOut:
    """签发 access + refresh 对；refresh 原文返回、hash 存库（03 §1）。"""
    # 若 user 尚未落库（register 新插入），先 flush 取回自增 id，避免写空 user_id
    db.flush()
    access = security.create_access_token(user.id)
    raw, token_hash = security.create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=_utcnow() + timedelta(seconds=security.refresh_ttl_seconds()),
        )
    )
    return TokensOut(
        access_token=access,
        refresh_token=raw,
        expires_in=settings.jwt_access_minutes * 60,
    )


def _auth_result(db: Session, user: User) -> AuthResult:
    tokens = _issue_tokens(db, user)
    db.commit()
    return AuthResult(user=UserOut.model_validate(user), tokens=tokens)


def register(db: Session, data: RegisterIn) -> AuthResult:
    username = data.username.strip() if data.username else None
    email = data.email.strip().lower() if data.email else None

    # 预检唯一性 → 409（清晰措辞）；最终由唯一约束兜底并发。
    if username is not None:
        if db.execute(select(User.id).where(User.username == username)).first():
            raise BizError("用户名已存在", status=409, code="CONFLICT")
    if email is not None:
        if db.execute(select(User.id).where(User.email == email)).first():
            raise BizError("邮箱已存在", status=409, code="CONFLICT")

    user = User(
        username=username,
        email=email,
        password_hash=security.hash_password(data.password),
        is_admin=False,  # 04 §8：注册不可提权
        is_active=True,
    )
    db.add(user)
    try:
        result = _auth_result(db, user)
    except IntegrityError:
        db.rollback()
        raise BizError("用户名或邮箱已存在", status=409, code="CONFLICT")
    return result


def login(db: Session, data: LoginIn) -> AuthResult:
    account = data.account.strip()
    email_q = account.lower()
    user = db.execute(
        select(User).where(or_(User.username == account, User.email == email_q))
    ).scalar_one_or_none()

    # 统一 401：用户不存在 / 密码错 同一措辞（06 §4 防枚举）
    if user is None or not security.verify_password(data.password, user.password_hash):
        raise BizError("账号或密码错误", status=401, code="BAD_CREDENTIALS")

    # 参数升级顺带重哈希
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(data.password)

    if not user.is_active:
        # 06 §1：禁用用户 403（区别于未认证 401）
        raise BizError("用户已被禁用", status=403, code="FORBIDDEN")

    return _auth_result(db, user)


def refresh(db: Session, data: RefreshIn) -> RefreshOut:
    token_hash = security.hash_token(data.refresh_token)
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    now = _utcnow()
    # 无效 / 已轮换 / 过期 → 统一 401 REFRESH_INVALID
    if row is None or row.is_revoked or row.expires_at <= now:
        raise BizError("refresh 令牌无效", status=401, code="REFRESH_INVALID")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise BizError("refresh 令牌无效", status=401, code="REFRESH_INVALID")

    # 轮换：旧令牌置 revoked（03 铁律防重放）
    row.revoked_at = now
    access = security.create_access_token(user.id)
    raw, new_hash = security.create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=now + timedelta(seconds=security.refresh_ttl_seconds()),
        )
    )
    db.commit()
    return RefreshOut(
        access_token=access,
        refresh_token=raw,
        expires_in=settings.jwt_access_minutes * 60,
    )


def change_password(db: Session, user: User, data: ChangePasswordIn) -> None:
    if not security.verify_password(data.old_password, user.password_hash):
        raise BizError("原密码错误", status=422, code="VALIDATION")
    user.password_hash = security.hash_password(data.new_password)
    # 06 §4：改密后所有 refresh 令牌吊销（踢下线）
    now = _utcnow()
    for tok in user.refresh_tokens:
        if tok.revoked_at is None:
            tok.revoked_at = now
    db.commit()


def logout(db: Session, refresh_token: str) -> None:
    """幂等登出：吊销指定 refresh（不存在/已吊销均视为成功）。"""
    token_hash = security.hash_token(refresh_token)
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()
