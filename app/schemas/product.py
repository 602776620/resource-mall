"""商品请求/响应模型（04 §4/§6）。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = (
    ("tutorial", "教程"),
    ("template", "模板"),
    ("material", "素材"),
    ("ai_asset", "AI 资源"),
    ("other", "其他"),
)


class CategoryOut(BaseModel):
    key: str
    label: str


class MediaItem(BaseModel):
    kind: Literal["image", "file"]
    url: str  # 签名短链 /media/<token>（预览）或原相对路径（管理端展示）
    name: str | None = None


class ProductOut(BaseModel):
    """列表/详情通用（04 §4 响应模型）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subtitle: str | None = None
    category: str
    tags: list[str]
    price_cents: int
    original_price_cents: int | None = None
    cover_image: str | None = None
    preview_media: list[MediaItem]
    file_name: str | None = None
    file_size: int | None = None
    is_listed: bool
    created_at: str


class ProductDetailOut(ProductOut):
    description: str | None = None


class Paged(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
