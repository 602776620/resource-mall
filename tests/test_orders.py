"""T06 订单与核销（09 §2-T06）：服务端算价 / 券抵扣 / 0 元单 / 取消·超时回滚券 /
核销工作台队列 / 核销并发 409 / 撤销必填理由 / 审计日志。打真实 mall_test 对拍。"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core import security
from app.db.models import AuditLog, Coupon, CouponUsage, Order, Product, User

API = "/api/v1"


# ---- 辅助 ----

def _sess(t):
    return t.session if hasattr(t, "session") else t


def _mk_user(target, *, username="alice", email=None, admin=False, active=True):
    """email 缺省由 username 派生，保证同一测试内多用户不撞 uq_users_email。"""
    db = _sess(target)
    u = User(
        username=username, email=email if email is not None else f"{username}@x.com",
        password_hash=security.hash_password("passw0rd"),
        is_admin=admin, is_active=active,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_product(target, *, title="t", price=10000, listed=True, cover=None):
    db = _sess(target)
    p = Product(
        title=title, category="other", tags=[],
        price_cents=price, is_listed=listed,
        file_url="downloads/x.zip" if listed else None,
        file_size=123 if listed else None,
        file_name="x.zip" if listed else None,
        cover_image=cover,
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


def _mk_coupon(target, *, code="CAAAAAAAAAA", ctype="fixed", value=1000,
               max_uses=1, active=True, used=0, from_offset=-1, to_offset=1):
    """from_offset/to_offset 为相对 now 的天数偏移（默认 [-1, +1] 即当前有效）。
    过期券：from_offset=-2, to_offset=-1（区间在 now 之前）。"""
    db = _sess(target)
    now = datetime.now(timezone.utc)
    vf = now + timedelta(days=from_offset)
    vt = now + timedelta(days=to_offset)
    # 管理员 username/email 由 code 派生，保证同测试多张券不撞唯一约束
    admin = _mk_user(target, username=f"cpadmin{code}", admin=True)
    c = Coupon(
        code=code, type=ctype, value=value, max_uses=max_uses, used_count=used,
        valid_from=vf, valid_to=vt, is_active=active, created_by=admin.id,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _auth(u: User):
    return {"Authorization": f"Bearer {security.create_access_token(u.id)}"}


def _get_order(db, order_no):
    return db.execute(select(Order).where(Order.order_no == order_no)).scalar_one()


def _oid(db, order_no):
    return _get_order(db, order_no).id


def _order_no(client, *, price=10000, coupon=None, admin_user=None):
    """直接经 API 下单，返回 order_no。"""
    u = _mk_user(client, username=f"buyer{price}{(coupon or 'none')[:6]}")
    p = _mk_product(client, price=price)
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": coupon},
                    headers=_auth(u))
    assert r.status_code == 201, r.text
    return r.json()["order_no"], u, p


# ---- 1. 服务端算价（03 铁律 3）----

def test_pricing_server_side_ignores_forged_amount(client):
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    # 伪造 amount_cents / 任意金额字段 → 一律忽略
    r = client.post(f"{API}/orders",
                    json={"product_id": p.id, "amount_cents": 1, "price": 1, "total": 1},
                    headers=_auth(u))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["amount_cents"] == 10000  # 服务端按商品价算
    assert body["original_cents"] == 10000
    assert body["discount_cents"] == 0
    assert body["pay_status"] == "pending"


def test_order_unlisted_or_missing_404(client):
    u = _mk_user(client, username="alice")
    hidden = _mk_product(client, price=1000, listed=False)
    r = client.post(f"{API}/orders", json={"product_id": hidden.id}, headers=_auth(u))
    assert r.status_code == 404
    assert client.post(f"{API}/orders", json={"product_id": 99999},
                       headers=_auth(u)).status_code == 404


def test_order_requires_login(client):
    p = _mk_product(client, price=1000)
    r = client.post(f"{API}/orders", json={"product_id": p.id})
    assert r.status_code == 401


# ---- 2. 券抵扣：fixed / percent（03 铁律 3 / 05 §3）----

def test_fixed_coupon_discount(client, db):
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)  # ¥100
    _mk_coupon(client, code="CFIXED00001", ctype="fixed", value=3000, max_uses=5)  # 立减 ¥30
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CFIXED00001"},
                    headers=_auth(u))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["original_cents"] == 10000
    assert b["discount_cents"] == 3000
    assert b["amount_cents"] == 7000  # 10000-3000
    assert b["coupon_code"] == "CFIXED00001"


def test_percent_coupon_discount_floor(client, db):
    u = _mk_user(client, username="bob")
    p = _mk_product(client, price=9900)  # ¥99
    _mk_coupon(client, code="CPERCENT0001", ctype="percent", value=33, max_uses=5)  # 33%
    # floor(9900 * 33 / 100) = floor(3267) = 3267
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CPERCENT0001"},
                    headers=_auth(u))
    b = r.json()
    assert b["discount_cents"] == 3267, b
    assert b["amount_cents"] == 9900 - 3267


def test_fixed_coupon_capped_at_original(client, db):
    """fixed 券面额 > 商品价 → 抵扣封顶为商品价（min(value, orig)），实付 ≥0。"""
    u = _mk_user(client, username="cap")
    p = _mk_product(client, price=1000)  # ¥10
    _mk_coupon(client, code="CFIXCAP00001", ctype="fixed", value=5000, max_uses=5)  # 立减 ¥50 > ¥10
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CFIXCAP00001"},
                    headers=_auth(u))
    b = r.json()
    assert b["discount_cents"] == 1000
    assert b["amount_cents"] == 0


def test_zero_amount_order_flow(client, db):
    """0 元单：全额抵扣后 amount=0 仍成功创建（05 §3）。"""
    u = _mk_user(client, username="zero")
    p = _mk_product(client, price=1000)
    _mk_coupon(client, code="CZERO0000001", ctype="fixed", value=1000, max_uses=5)  # 正好全额
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CZERO0000001"},
                    headers=_auth(u))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["amount_cents"] == 0
    assert b["pay_status"] == "pending"
    # 0 元单可直接提交「我已付款」（说明≥5字；展示文案「0元单」，实际需凑满 5 字）
    r2 = client.post(f"{API}/orders/{b['order_no']}/paid-submitted", json={"note": "0元单全额抵扣"},
                     headers=_auth(u))
    assert r2.status_code == 200, r2.text
    assert r2.json()["paid_submitted_at"] is not None


def test_invalid_coupon_409(client, db):
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    # 不存在
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CDOESNOT0001"},
                    headers=_auth(u))
    assert r.status_code == 409 and r.json()["error"]["code"] == "COUPON_INVALID"
    # 超量（used_count >= max_uses）
    _mk_coupon(client, code="CFULL0000001", ctype="fixed", value=100, max_uses=1, used=1)
    r = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CFULL0000001"},
                    headers=_auth(u))
    assert r.status_code == 409 and r.json()["error"]["code"] == "COUPON_INVALID"
    # 停用
    _mk_coupon(client, code="CINACTIVE001", ctype="fixed", value=100, max_uses=5, active=False)
    assert client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CINACTIVE001"},
                       headers=_auth(u)).status_code == 409
    # 过期（区间在 now 之前）
    _mk_coupon(client, code="CEXPIRED0001", ctype="fixed", value=100, max_uses=5,
               from_offset=-2, to_offset=-1)
    assert client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CEXPIRED0001"},
                       headers=_auth(u)).status_code == 409


def test_coupon_precheck_no_detail_leak(client, db):
    """预检只回 valid 布尔 + 类型/值，不暴露已用次数/原因（04 §4 防探测）。"""
    _mk_coupon(client, code="CVALID000001", ctype="percent", value=20, max_uses=5)
    r = client.get(f"{API}/coupons/CVALID000001")
    assert r.status_code == 200
    b = r.json()
    assert b["valid"] is True and b["type"] == "percent" and b["value"] == 20
    # 不存在 / 超量 → valid=false 且不带 type/value
    assert client.get(f"{API}/coupons/CNOPE000000001").json() == {"valid": False}
    _mk_coupon(client, code="CPRECK0000001", ctype="fixed", value=100, max_uses=1, used=1)
    assert client.get(f"{API}/coupons/CPRECK0000001").json() == {"valid": False}


# ---- 3. 我的订单 / 仅本人 / 取消 / 我已付款 ----

def test_my_orders_only_own(client, db):
    a = _mk_user(client, username="alice")
    b = _mk_user(client, username="bob")
    p = _mk_product(client, price=10000)
    ra = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(a))
    rb = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(b))
    a_no = ra.json()["order_no"]; b_no = rb.json()["order_no"]
    # alice 只看到自己那单
    r = client.get(f"{API}/orders", headers=_auth(a))
    assert {it["order_no"] for it in r.json()["items"]} == {a_no}
    # 跨用户访问他人订单 → 404（防探测）
    assert client.get(f"{API}/orders/{b_no}", headers=_auth(a)).status_code == 404


def test_cancel_pending_then_conflict(client, db):
    a = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(a)).json()["order_no"]
    r = client.post(f"{API}/orders/{no}/cancel", headers=_auth(a))
    assert r.status_code == 200 and r.json()["pay_status"] == "cancelled"
    # 重复取消 → 409（非 pending）
    r2 = client.post(f"{API}/orders/{no}/cancel", headers=_auth(a))
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "CONFLICT"


def test_paid_submitted_then_already(client, db):
    a = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(a)).json()["order_no"]
    r = client.post(f"{API}/orders/{no}/paid-submitted", json={"note": "17:20 微信 尾号1234"},
                    headers=_auth(a))
    assert r.status_code == 200 and r.json()["paid_submitted_at"] is not None
    assert r.json()["paid_note"] == "17:20 微信 尾号1234"
    # 重复提交 → 409 ALREADY_SUBMITTED
    r2 = client.post(f"{API}/orders/{no}/paid-submitted", json={"note": "重复提交说明"},
                     headers=_auth(a))
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "ALREADY_SUBMITTED"
    # 说明 <5 字 → 422
    no2 = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(a)).json()["order_no"]
    assert client.post(f"{API}/orders/{no2}/paid-submitted", json={"note": "短"},
                       headers=_auth(a)).status_code == 422


# ---- 4. 券回滚：用户取消 / 超时取消（05 §3）----

def test_user_cancel_rolls_back_coupon(client, db):
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    c = _mk_coupon(client, code="CRCBK0000001", ctype="fixed", value=1000, max_uses=5)
    no = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CRCBK0000001"},
                     headers=_auth(u)).json()["order_no"]
    # 下单后券占用 +1，usage 行存在
    db.refresh(c)
    assert c.used_count == 1
    assert db.query(CouponUsage).filter_by(order_id=_oid(db, no)).count() == 1

    r = client.post(f"{API}/orders/{no}/cancel", headers=_auth(u))
    assert r.json()["pay_status"] == "cancelled"
    # 回滚：used_count-1，usage 删除
    db.refresh(c)
    assert c.used_count == 0
    assert db.query(CouponUsage).filter_by(order_id=_oid(db, no)).count() == 0


def test_timeout_cancel_rolls_back_coupon(client, db):
    """超时取消任务（expire_pending_orders）：pending 且过期 → cancelled + 券回滚。"""
    from app.services import order_service

    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    c = _mk_coupon(client, code="CTIMEOUT00001", ctype="fixed", value=1000, max_uses=5)
    no = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CTIMEOUT00001"},
                     headers=_auth(u)).json()["order_no"]
    # 把该订单 expire_at 改到过去（模拟 30min 已超）
    _get_order(db, no).expire_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    n = order_service.expire_pending_orders(db)
    assert n >= 1, n
    # 订单已取消 + 券回滚
    assert _get_order(db, no).pay_status == "cancelled"
    db.refresh(c)
    assert c.used_count == 0
    assert db.query(CouponUsage).filter_by(order_id=_oid(db, no)).count() == 0


def test_paid_order_revoke_keeps_coupon(client, db):
    """已 paid 订单撤销（revoke）不回滚券（05 §3：券已消耗，与撤销语义一致）。"""
    from app.services import order_service

    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    c = _mk_coupon(client, code="CNOBK0000001", ctype="fixed", value=1000, max_uses=5)
    no = client.post(f"{API}/orders", json={"product_id": p.id, "coupon_code": "CNOBK0000001"},
                     headers=_auth(u)).json()["order_no"]
    admin = _mk_user(client, username="adm1", admin=True)
    order_service.confirm_order(db, admin_id=admin.id, ip="10.0.0.1", order_no=no,
                                pay_channel="wechat", note=None)
    db.refresh(c)
    assert c.used_count == 1
    # 撤销 → 不回滚券
    order_service.revoke_order(db, admin_id=admin.id, ip="10.0.0.1", order_no=no,
                               reason="错核销处理")
    db.refresh(c)
    assert c.used_count == 1  # 保持不变
    assert db.query(CouponUsage).count() == 1  # usage 仍在


# ---- 5. 管理员核销工作台 / 核销并发 409 / 撤销理由 / 审计 ----

def test_admin_queue_is_submitted_pending_ascending(client, db):
    """核销工作台队列 = pending 且 paid_submitted 非空，按提交时间正序（05 §2 SOP 步骤1）。"""
    from app.services import order_service

    p = _mk_product(client, price=10000)
    u1 = _mk_user(client, username="u1")
    u2 = _mk_user(client, username="u2")
    u3 = _mk_user(client, username="u3")
    n1 = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u1)).json()["order_no"]
    n2 = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u2)).json()["order_no"]
    n3 = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u3)).json()["order_no"]
    # 提交顺序：u1 先、u2 后（u3 不提交）
    _get_order(db, n1).paid_submitted_at = datetime.now(timezone.utc) - timedelta(seconds=100)
    _get_order(db, n1).paid_note = "说明1"
    _get_order(db, n2).paid_submitted_at = datetime.now(timezone.utc)
    _get_order(db, n2).paid_note = "说明2"
    db.commit()

    items, total = order_service.list_admin_orders(
        db, status=None, submitted=True, order_no=None, user=None, page=1, page_size=100)
    assert total == 2, total  # 只含已提交的（n3 未提交不计）
    assert [it.order_no for it in items] == [n1, n2]  # 提交时间正序


def test_admin_confirm_then_concurrent_409(client, db):
    """核销并发 409：已核销(paid)订单再次核销 → rowcount=0 → 409 CONFLICT（03 铁律1）。"""
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u)).json()["order_no"]
    a = _mk_user(client, username="adm", admin=True)
    # 首次核销成功
    r = client.post(f"{API}/admin/orders/{no}/confirm", json={"pay_channel": "wechat"},
                    headers=_auth(a))
    assert r.status_code == 200 and r.json()["pay_status"] == "paid", r.text
    # 再次核销（并发模拟）→ 409
    r2 = client.post(f"{API}/admin/orders/{no}/confirm", json={"pay_channel": "alipay"},
                     headers=_auth(a))
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "CONFLICT"


def test_admin_revoke_requires_reason_min5(client, db):
    """撤销：非 paid → 409；理由 <5 字 → 422；≥5 字 → revoked。"""
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u)).json()["order_no"]
    a = _mk_user(client, username="adm", admin=True)
    # pending 直接撤销 → 409（非 paid）
    r = client.post(f"{API}/admin/orders/{no}/revoke", json={"reason": "足够长的撤销理由"},
                    headers=_auth(a))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    # 核销后再撤销：理由 <5 字 → 422
    client.post(f"{API}/admin/orders/{no}/confirm", json={"pay_channel": "wechat"},
                headers=_auth(a))
    r2 = client.post(f"{API}/admin/orders/{no}/revoke", json={"reason": "短"}, headers=_auth(a))
    assert r2.status_code == 422
    # 理由 ≥5 字 → 成功 revoked
    r3 = client.post(f"{API}/admin/orders/{no}/revoke", json={"reason": "错核销，重新收款"},
                     headers=_auth(a))
    assert r3.status_code == 200 and r3.json()["pay_status"] == "revoked"


def test_admin_confirm_revoke_audit_logs(client, db):
    """审计日志：confirm/revoke 含操作人/理由（05 §2 步骤5，06 §7）。"""
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u)).json()["order_no"]
    a = _mk_user(client, username="adm", admin=True)
    client.post(f"{API}/admin/orders/{no}/confirm", json={"pay_channel": "alipay", "note": "三方比对通过"},
                headers=_auth(a))
    client.post(f"{API}/admin/orders/{no}/revoke", json={"reason": "用户投诉，撤销重收"},
                headers=_auth(a))
    logs = db.execute(select(AuditLog).where(AuditLog.target_type == "order")).scalars().all()
    by_action = {lg.action: lg for lg in logs}
    assert "order.confirm" in by_action and "order.revoke" in by_action
    assert by_action["order.confirm"].admin_id == a.id
    assert by_action["order.confirm"].reason == "三方比对通过"
    assert by_action["order.revoke"].admin_id == a.id
    assert by_action["order.revoke"].reason == "用户投诉，撤销重收"


def test_admin_requires_admin_role(client, db):
    """核销/撤销/列表 非管理员 → 403（06 §1 红线1）。"""
    u = _mk_user(client, username="alice")  # 普通用户
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id}, headers=_auth(u)).json()["order_no"]
    assert client.get(f"{API}/admin/orders", headers=_auth(u)).status_code == 403
    assert client.post(f"{API}/admin/orders/{no}/confirm", json={"pay_channel": "wechat"},
                       headers=_auth(u)).status_code == 403
    assert client.post(f"{API}/admin/orders/{no}/revoke", json={"reason": "足够长的撤销理由"},
                       headers=_auth(u)).status_code == 403
