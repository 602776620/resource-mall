"""订单路由（04 §5 用户 / §6 管理员核销工作台）。"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.db.models import Product, User
from app.services import download_service
from app.schemas.order import (
    AdminOrderConfirmIn,
    AdminOrderDetailOut,
    AdminOrderOut,
    AdminOrderRevokeIn,
    OrderCreateIn,
    OrderDetailOut,
    OrderOut,
    PaidSubmitIn,
)
from app.schemas.product import Paged
from app.services import order_service

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ---- 用户侧（04 §5，需登录）----


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    data: OrderCreateIn,
    request: Request,  # noqa: ARG001 - IP 仅下单限流用（T10），此处占位
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service._order_out(
        order_service.create_order(
            db, user_id=current.id, product_id=data.product_id, coupon_code=data.coupon_code
        )
    )


@router.get("", response_model=Paged)
def my_orders(
    status: str | None = Query(None, pattern="^(pending|paid|revoked|cancelled)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Paged:
    items, total = order_service.list_user_orders(
        db, user_id=current.id, status=status, page=page, page_size=page_size
    )
    return Paged(items=[i.model_dump() for i in items], total=total, page=page, page_size=page_size)


@router.get("/{order_no}", response_model=OrderDetailOut)
def order_detail(order_no: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrderDetailOut:
    o = order_service.get_user_order(db, user_id=current.id, order_no=order_no)
    return order_service.order_detail_out(o, db.get(Product, o.product_id))


@router.post("/{order_no}/cancel", response_model=OrderOut)
def cancel_order(order_no: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrderOut:
    return order_service._order_out(order_service.cancel_order(db, user_id=current.id, order_no=order_no))


@router.post("/{order_no}/paid-submitted", response_model=OrderOut)
def paid_submitted(
    order_no: str, data: PaidSubmitIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> OrderOut:
    return order_service._order_out(
        order_service.submit_paid(db, user_id=current.id, order_no=order_no, note=data.note)
    )


# ---- 下载签发（04 §5 / 05 §4 / T07）----
# 校验链顺序：本人+存在→404；paid→403 ORDER_NOT_PAID；Redis 7 天 50 次→429
# （降级 DB 兜底、双挂 503）；消费前复核 paid；写 download_logs；302 → /files/{token}


@router.get("/{order_no}/download", response_model=None, include_in_schema=True)
def download(
    order_no: str,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    token = download_service.issue(
        db,
        user_id=current.id,
        order_no=order_no,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # 302 到文件短链端点：用相对 Location（/api/v1/files/{token}），
    # 浏览器按当前 origin 解析 → 经 Vite proxy 直达后端，不泄漏内部 Host（04 §5）。
    location = request.url_for("files_download", token=token).path
    return RedirectResponse(url=location, status_code=302)


# ---- 管理员侧（04 §6，需管理员；06 §1 红线 1）----

admin_router = APIRouter(dependencies=[Depends(require_admin)])


@admin_router.get("", response_model=Paged)
def admin_orders(
    status: str | None = Query(None, pattern="^(pending|paid|revoked|cancelled)$"),
    submitted: bool | None = Query(None),
    order_no: str | None = Query(None),
    user: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Paged:
    items, total = order_service.list_admin_orders(
        db, status=status, submitted=submitted, order_no=order_no, user=user, page=page, page_size=page_size
    )
    return Paged(items=[i.model_dump() for i in items], total=total, page=page, page_size=page_size)


@admin_router.get("/{order_no}", response_model=AdminOrderDetailOut)
def admin_order_detail(order_no: str, db: Session = Depends(get_db)) -> AdminOrderDetailOut:
    return order_service.get_admin_order_detail(db, order_no)


@admin_router.post("/{order_no}/confirm", response_model=OrderOut)
def admin_confirm(
    order_no: str,
    data: AdminOrderConfirmIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service._order_out(
        order_service.confirm_order(
            db,
            admin_id=admin.id,
            ip=_client_ip(request),
            order_no=order_no,
            pay_channel=data.pay_channel,
            note=data.note,
        )
    )


@admin_router.post("/{order_no}/revoke", response_model=OrderOut)
def admin_revoke(
    order_no: str,
    data: AdminOrderRevokeIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service._order_out(
        order_service.revoke_order(
            db, admin_id=admin.id, ip=_client_ip(request), order_no=order_no, reason=data.reason
        )
    )
