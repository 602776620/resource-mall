"""products 表（03 §1）。金额分（BIGINT）、tags TEXT[]、preview_media JSONB。"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_cents > 0", name="ck_products_price_positive"),
        CheckConstraint(
            "original_price_cents IS NULL OR original_price_cents >= price_cents",
            name="ck_products_original_gte_price",
        ),
        Index("ix_products_listed_created", "is_listed", text("created_at DESC")),
        Index("ix_products_category", "category"),
        Index("ix_products_listed_price", "is_listed", "price_cents"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # tutorial/template/material/ai_asset/other（03 §1 / 04 §4 /categories）
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default=text("'{}'"))
    price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String(512), nullable=True)  # uploads/ 相对路径
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # 入库前白名单过滤（06 §5）
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 原始文件名（展示）
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # downloads/ 相对路径，不可公开
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 字节
    # [{kind:"image"|"file", url, name?}]；image≤9、file≤3
    preview_media: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'::json")
    )
    is_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product id={self.id} title={self.title!r} listed={self.is_listed}>"
