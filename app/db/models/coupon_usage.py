"""coupon_usages 表（03 §1）。一券一单：order_id UNIQUE。防重放靠 03 铁律 2 试扣。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CouponUsage(Base):
    __tablename__ = "coupon_usages"
    __table_args__ = (
        Index("ix_coupon_usages_code_order", "code", "order_id"),
        Index("uq_coupon_usages_order", "order_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        ForeignKey("coupons.code", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    discount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CouponUsage code={self.code!r} order={self.order_id}>"
