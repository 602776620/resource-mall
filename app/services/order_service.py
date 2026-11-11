"""订单业务逻辑（04 §5/§6 / 03 铁律 1/2/3 / 05 §1-§3）。依赖注入 db，可单测。"""
import math
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.core.exceptions import BizError
from app.db.models import Coupon, CouponUsage, DownloadLog, Order, Product, User
from app.schemas.order import (
    AdminOrderDetailOut,
    AdminOrderOut,
    OrderDetailOut,
    OrderOut,
)
from app.services import audit_service


ORDER_NO_ALPHABET = string.ascii_uppercase + string.digits


def _gen_order_no() -> str:
    """RM + 14 位 UTC 时间戳 + 6 位大写随机字母数字（03 §1）。冲突靠唯一约束兜底。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand = "".join(secrets.choice(ORDER_NO_ALPHABET) for _ in range(6))
    return f"RM{ts}{rand}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---- 券算价（03 铁律 3 / 05 §3）----

def coupon_discount(coupon: Coupon, original_cents: int) -> int:
    """抵扣额：percent=floor(orig*value/100)；fixed=min(value, orig)。0 元单允许（05 §3）。"""
    if coupon.type == "percent":
        return int(math.floor(original_cents * coupon.value / 100))
    return min(coupon.value, original_cents)


# ---- 序列化（04 §5/§6）----

def _order_out(o: Order) -> OrderOut:
    return OrderOut(
        order_no=o.order_no,
        product_id=o.product_id,
        product_title=o.product_title_snapshot,
        amount_cents=o.amount_cents,
        original_cents=o.original_cents,
        coupon_code=o.coupon_code,
        discount_cents=o.discount_cents,
        pay_status=o.pay_status,
        pay_channel=o.pay_channel,
        paid_submitted_at=_fmt(o.paid_submitted_at),
        paid_note=o.paid_note,
        paid_at=_fmt(o.paid_at),
        expire_at=_fmt(o.expire_at),
        created_at=_fmt(o.created_at),
    )


def order_detail_out(o: Order, p: Product | None) -> OrderDetailOut:
    return OrderDetailOut(
        **_order_out(o).model_dump(),
        file_name=p.file_name if p else None,
        file_size=p.file_size if p else None,
        revoked_at=_fmt(o.revoked_at),
        revoke_reason=o.revoke_reason,
    )


# ---- 用户侧（04 §5）----

def create_order(db: Session, *, user_id: int, product_id: int, coupon_code: str | None = None) -> Order:
    """服务端算价 + 券原子试扣（03 铁律 2/3）。同事务，券试扣失败整体回滚。"""
    p = db.get(Product, product_id)
    if p is None or not p.is_listed:
        # 06 §1 红线 3：未上架/不存在对外 404 防探测
        raise BizError("资源不存在", status=404, code="NOT_FOUND")

    original = p.price_cents
    discount = 0
    used_code: str | None = None
    if coupon_code:
        c = db.get(Coupon, coupon_code)
        # 03 铁律 2：行级有效性以试扣 UPDATE 为准；此处仅预检取抵扣额（统一 409 措辞，不暴露明细）
        if c is None:
            raise BizError("券码无效", status=409, code="COUPON_INVALID")
        discount = coupon_discount(c, original)
        used_code = coupon_code

    now = _utcnow()
    order = Order(
        order_no=_gen_order_no(),
        user_id=user_id,
        product_id=product_id,
        product_title_snapshot=p.title[:120],
        amount_cents=max(0, original - discount),  # 0 元单允许（05 §3）
        original_cents=original,
        coupon_code=used_code,
        discount_cents=discount,
        pay_status="pending",
        expire_at=now + timedelta(minutes=settings.order_expire_minutes),
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    db.flush()  # 拿到 order.id 供 coupon_usages

    if used_code is not None:
        # 03 铁律 2：试扣 UPDATE，rowcount=0 → 整体回滚（超量/停用/过期/并发抢占）
        res = db.execute(
            update(Coupon)
            .where(
                Coupon.code == used_code,
                Coupon.is_active.is_(True),
                Coupon.used_count < Coupon.max_uses,
                now >= Coupon.valid_from,
                now <= Coupon.valid_to,
            )
            .values(used_count=Coupon.used_count + 1)
        )
        if res.rowcount == 0:
            raise BizError("券码无效", status=409, code="COUPON_INVALID")
        db.add(
            CouponUsage(
                code=used_code,
                order_id=order.id,
                discount_cents=discount,
                used_at=now,
            )
        )
    db.commit()
    db.refresh(order)
    return order


def get_user_order(db: Session, *, user_id: int, order_no: str) -> Order:
    """仅本人；他人/不存在一律 404（04 §5 红线 3 防探测）。"""
    o = db.execute(
        select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
    ).scalar_one_or_none()
    if o is None:
        raise BizError("订单不存在", status=404, code="NOT_FOUND")
    return o


def list_user_orders(
    db: Session, *, user_id: int, status: str | None, page: int, page_size: int
) -> tuple[list[OrderOut], int]:
    q = select(Order).where(Order.user_id == user_id)
    if status:
        q = q.where(Order.pay_status == status)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    items = list(
        db.execute(
            q.order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    return [_order_out(o) for o in items], total


def cancel_order(db: Session, *, user_id: int, order_no: str) -> Order:
    """pending→cancelled 条件更新（铁律 1）。释放券占用（05 §3：取消都回滚券）。"""
    o = get_user_order(db, user_id=user_id, order_no=order_no)
    res = db.execute(
        update(Order)
        .where(Order.id == o.id, Order.pay_status == "pending")
        .values(pay_status="cancelled", updated_at=_utcnow())
    )
    if res.rowcount == 0:
        raise BizError("订单状态已变化，无法取消", status=409, code="CONFLICT")
    _rollback_coupon(db, o)
    db.commit()
    db.refresh(o)
    return o


def submit_paid(db: Session, *, user_id: int, order_no: str, note: str) -> Order:
    """仅 pending：置 paid_submitted_at/paid_note，进入核销队列（04 §5）。重复提交→409。"""
    o = get_user_order(db, user_id=user_id, order_no=order_no)
    if o.pay_status != "pending":
        raise BizError("订单不可提交支付", status=409, code="CONFLICT")
    if o.paid_submitted_at is not None:
        raise BizError("已提交支付说明，请勿重复操作", status=409, code="ALREADY_SUBMITTED")
    o.paid_submitted_at = _utcnow()
    o.paid_note = note
    o.updated_at = _utcnow()
    db.commit()
    db.refresh(o)
    return o


# ---- 超时取消任务（05 §1/§7，幂等，单实例）----

def expire_pending_orders(db: Session) -> int:
    """扫 pending 且 expire_at<now → cancelled（批量条件更新）。逐单回滚券占用。返回取消数。"""
    now = _utcnow()
    res = db.execute(
        update(Order)
        .where(Order.pay_status == "pending", Order.expire_at < now)
        .values(pay_status="cancelled", updated_at=now)
    )
    n = res.rowcount
    if n:
        # 回滚被取消订单占用的券（05 §3：used_count-1 + 删 usage，同事务）
        cancelled = db.execute(
            select(Order)
            .where(Order.pay_status == "cancelled", Order.expire_at < now)
        ).scalars()
        for o in cancelled:
            _rollback_coupon(db, o)
        db.commit()
    return n


def _rollback_coupon(db: Session, o: Order) -> None:
    """券回滚：used_count-1 + 删该订单 usage（05 §3）。无券则跳过。"""
    if o.coupon_code is None:
        return
    db.execute(
        update(Coupon)
        .where(Coupon.code == o.coupon_code)
        .values(used_count=Coupon.used_count - 1)
    )
    db.execute(sa_delete(CouponUsage).where(CouponUsage.order_id == o.id))


# ---- 管理员侧（04 §6，05 §2 SOP）----

def _get_admin_order(db: Session, order_no: str) -> Order:
    o = db.execute(select(Order).where(Order.order_no == order_no)).scalar_one_or_none()
    if o is None:
        raise BizError("订单不存在", status=404, code="NOT_FOUND")
    return o


def confirm_order(
    db: Session, *, admin_id: int, ip: str | None, order_no: str, pay_channel: str, note: str | None
) -> Order:
    """核销 pending→paid（铁律 1 条件更新），rowcount=0→409（并发核销/已取消）。审计 order.confirm。"""
    o = _get_admin_order(db, order_no)
    res = db.execute(
        update(Order)
        .where(Order.id == o.id, Order.pay_status == "pending")
        .values(pay_status="paid", pay_channel=pay_channel, paid_at=_utcnow(), updated_at=_utcnow())
    )
    if res.rowcount == 0:
        raise BizError("订单状态已变化（可能已被核销或取消）", status=409, code="CONFLICT")
    audit_service.record(
        db, admin_id=admin_id, action="order.confirm",
        target_type="order", target_id=o.id, reason=note, ip=ip,
    )
    db.commit()
    db.refresh(o)
    return o


def revoke_order(db: Session, *, admin_id: int, ip: str | None, order_no: str, reason: str) -> Order:
    """撤销 paid→revoked（铁律 1），理由必填（Pydantic 保证≥5 字）。不回滚券（05 §3）。审计 order.revoke。"""
    o = _get_admin_order(db, order_no)
    res = db.execute(
        update(Order)
        .where(Order.id == o.id, Order.pay_status == "paid")
        .values(pay_status="revoked", revoked_at=_utcnow(), revoke_reason=reason, updated_at=_utcnow())
    )
    if res.rowcount == 0:
        raise BizError("仅已支付订单可撤销", status=409, code="CONFLICT")
    audit_service.record(
        db, admin_id=admin_id, action="order.revoke",
        target_type="order", target_id=o.id, reason=reason, ip=ip,
    )
    db.commit()
    db.refresh(o)
    return o


def list_admin_orders(
    db: Session,
    *,
    status: str | None,
    submitted: bool | None,
    order_no: str | None,
    user: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AdminOrderOut], int]:
    """全量订单（带用户名/邮箱）。submitted=true → 核销工作台队列（pending 且已提交，正序 05 §2）。"""
    U = aliased(User)
    stmt = select(Order, U).join(U, U.id == Order.user_id)
    if status:
        stmt = stmt.where(Order.pay_status == status)
    if submitted:
        stmt = stmt.where(Order.pay_status == "pending", Order.paid_submitted_at.isnot(None))
    if order_no:
        stmt = stmt.where(Order.order_no == order_no)
    if user:
        like = f"%{user}%"
        stmt = stmt.where((U.username.ilike(like)) | (U.email.ilike(like)))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    if submitted:
        # 核销队列：按提交时间正序（05 §2 SOP 步骤 1）
        rows = db.execute(
            stmt.order_by(Order.paid_submitted_at.asc(), Order.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    else:
        rows = db.execute(
            stmt.order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

    out = [
        AdminOrderOut(
            **_order_out(o).model_dump(),
            user_id=o.user_id,
            username=u.username,
            email=u.email,
        )
        for o, u in rows
    ]
    return out, total


def get_admin_order_detail(db: Session, order_no: str) -> AdminOrderDetailOut:
    o = _get_admin_order(db, order_no)
    u = db.get(User, o.user_id)
    p = db.get(Product, o.product_id)
    logs = list(
        db.execute(
            select(DownloadLog)
            .where(DownloadLog.order_id == o.id)
            .order_by(DownloadLog.created_at.desc())
        ).scalars()
    )
    return AdminOrderDetailOut(
        **_order_out(o).model_dump(),
        user_id=o.user_id,
        username=u.username if u else None,
        email=u.email if u else None,
        file_name=p.file_name if p else None,
        file_size=p.file_size if p else None,
        revoked_at=_fmt(o.revoked_at),
        revoke_reason=o.revoke_reason,
        download_logs=[
            {"ip": lg.ip, "user_agent": lg.user_agent, "created_at": lg.created_at.isoformat()}
            for lg in logs
        ],
    )
