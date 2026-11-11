"""coupons 表（03 §1）。code 为 PK：C + 11 位大写字母数字（批量生成）。"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint(
            "type IN ('fixed','percent')", name="ck_coupons_type"
        ),
        CheckConstraint("value > 0", name="ck_coupons_value_pos"),
        CheckConstraint("max_uses >= 1", name="ck_coupons_max_uses"),
        CheckConstraint("used_count >= 0", name="ck_coupons_used_count"),
    )

    # PK 即券码（无独立 id）
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(8), nullable=False)  # fixed / percent
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)  # fixed=分；percent=1~95
    max_uses: Mapped[int] = mapped_column(nullable=False)
    used_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default=text("0"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Coupon code={self.code!r} type={self.type} used={self.used_count}/{self.max_uses}>"
