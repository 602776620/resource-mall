"""券码路由（04 §4 预检）。管理端生成/停用/明细属 T08，路由另挂 admin_router。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.db.models import Coupon
from app.schemas.order import CouponCheckOut

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/coupons/{code}", response_model=CouponCheckOut, response_model_exclude_none=True)
def check_coupon(code: str, db: Session = Depends(get_db)) -> CouponCheckOut:
    """有效性预检（04 §4）：只给 valid 布尔 + 类型/值，不暴露已用次数/原因明细（防探测）。
    invalid 时 type/value 省略（exclude_none），响应恒为 {"valid": false}。"""
    c = db.get(Coupon, code)
    now_valid = (
        c is not None
        and c.is_active
        and c.used_count < c.max_uses
        and c.valid_from <= _utcnow()
        and c.valid_to >= _utcnow()
    )
    if not now_valid:
        # 统一措辞，不区分「不存在/停用/超量/过期」
        return CouponCheckOut(valid=False)
    return CouponCheckOut(valid=True, type=c.type, value=c.value)
