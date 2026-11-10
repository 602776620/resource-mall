"""认证相关请求/响应模型（04 §3）。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

USERNAME_RE = r"^[a-zA-Z0-9_]{3,32}$"


def _strong_password(v: str) -> str:
    """04 §3：密码 8~64 位，至少含字母和数字。"""
    if not (8 <= len(v) <= 64):
        raise ValueError("密码长度需 8~64 位")
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("密码需同时包含字母和数字")
    return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None = None  # 04 §3：username/email 二选一，username 可空
    email: str | None = None
    is_admin: bool
    created_at: datetime | None = None


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # access 剩余秒数


class AuthResult(BaseModel):
    user: UserOut
    tokens: TokensOut


class RegisterIn(BaseModel):
    username: str | None = Field(default=None, pattern=USERNAME_RE)
    email: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=64)
    password_confirm: str

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _strong_password(v)

    @model_validator(mode="after")
    def _check(self) -> "RegisterIn":
        # 04 §3：username/email 二选一必填（03 约束 username NOT NULL → 至少 username）
        if not self.username and not self.email:
            raise ValueError("username 与 email 至少提供一项")
        if self.password != self.password_confirm:
            raise ValueError("两次密码不一致")
        if self.email:
            self.email = self.email.strip().lower()
        return self


class LoginIn(BaseModel):
    account: str  # 用户名或邮箱
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class RefreshOut(BaseModel):
    access_token: str
    refresh_token: str  # 新令牌（轮换）
    expires_in: int


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _npw(cls, v: str) -> str:
        return _strong_password(v)


class LogoutIn(BaseModel):
    refresh_token: str
