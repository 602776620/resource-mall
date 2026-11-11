"""订单请求/响应模型（04 §5 用户 / §6 管理员）。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import Paged


class OrderCreateIn(BaseModel):
    product_id: int
    coupon_code: str | None = Field(None, max_length=32)
    # 03 铁律 3：服务端算价——不接收任何金额字段（伪造 amount 无效）。


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_no: str
    product_id: int
    product_title: str
    amount_cents: int
    original_cents: int
    coupon_code: str | None = None
    discount_cents: int
    pay_status: str
    pay_channel: str | None = None
    paid_submitted_at: str | None = None
    paid_note: str | None = None
    paid_at: str | None = None
    expire_at: str
    created_at: str


class OrderDetailOut(OrderOut):
    file_name: str | None = None
    file_size: int | None = None
    revoked_at: str | None = None
    revoke_reason: str | None = None


class PaidSubmitIn(BaseModel):
    note: str = Field(min_length=5, max_length=500)


class CouponCheckOut(BaseModel):
    """券码有效性预检（04 §4）：只给 valid 布尔 + 类型/值，不暴露已用次数/原因明细。"""

    valid: bool
    type: Literal["fixed", "percent"] | None = None
    value: int | None = None


class AdminOrderOut(OrderOut):
    user_id: int
    username: str | None = None
    email: str | None = None


class AdminOrderDetailOut(AdminOrderOut):
    file_name: str | None = None
    file_size: int | None = None
    revoked_at: str | None = None
    revoke_reason: str | None = None
    download_logs: list[dict] = Field(default_factory=list)


class AdminOrderConfirmIn(BaseModel):
    pay_channel: Literal["wechat", "alipay"]
    note: str | None = Field(None, max_length=200)


class AdminOrderRevokeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=200)
