"""orders 表（03 §1）。schema 前置到 T04（DELETE 守卫需查订单存在性）；业务逻辑 T06。

状态机 pay_status: pending → paid | cancelled；paid → revoked（03 §2）。
"""
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


PAY_STATUSES = ("pending", "paid", "revoked", "cancelled")
PAY_CHANNELS = ("wechat", "alipay")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "pay_status IN ('pending','paid','revoked','cancelled')",
            name="ck_orders_pay_status",
        ),
        CheckConstraint(
            "pay_channel IS NULL OR pay_channel IN ('wechat','alipay')",
            name="ck_orders_pay_channel",
        ),
        CheckConstraint("amount_cents >= 0", name="ck_orders_amount_nonneg"),
        Index("ix_orders_user_paystatus", "user_id", "pay_status"),
        Index("ix_orders_paystatus_submitted", "pay_status", "paid_submitted_at"),
        Index("ix_orders_product", "product_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # RM + 14 位 UTC 时间戳 + 6 位大写字母数字；冲突重试≤3（靠唯一约束兜底）
    order_no: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_title_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 实付（券后）
    original_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 券前
    coupon_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 未用=NULL
    discount_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    pay_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default=text("'pending'")
    )
    pay_channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    paid_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # created+30min
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order order_no={self.order_no!r} status={self.pay_status}>"
