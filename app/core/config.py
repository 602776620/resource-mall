"""应用配置：pydantic-settings 读取 .env（08 §4，密钥不入库）。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库 / 缓存
    db_dsn: str = "postgresql+psycopg://mall:changeme@127.0.0.1:5432/mall"
    redis_dsn: str = "redis://:changeme@127.0.0.1:6379/0"

    # 认证
    jwt_secret: str = "dev-only"
    jwt_access_minutes: int = 15
    jwt_refresh_days: int = 7

    # 签名短链 HMAC 密钥（04 §7）
    secret_file: str = "dev-only"

    # 文件（05 §8 / 07 §7）
    upload_root: str = "uploads"
    download_root: str = "downloads"
    max_resource_mb: int = 2048

    # 其他
    cors_origins: str = "http://127.0.0.1:5173"
    order_expire_minutes: int = 30
    download_quota: int = 50
    download_window_days: int = 7
    app_env: str = "dev"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
