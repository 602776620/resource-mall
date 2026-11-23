"""T07 下载（09 §2-T07）：校验链 / 限流 7 天 50 次 / 15min 过期 410 /
Range 断点续传 / 中文文件名 / download_logs 留痕 / 撤销后旧链 403 / Redis 降级。
打真实 mall_test + Redis。"""
import time

import pytest
from sqlalchemy import select

from app.core import security, storage
from app.core.config import settings
from app.core.deps import get_redis
from app.db.models import DownloadLog, Order, Product, User

API = "/api/v1"

_CREATED_FILES: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup_files():
    """每个测试后物理删除本模块创建的资源文件（conftest 只清库不清盘）。"""
    yield
    for rel in _CREATED_FILES:
        storage.delete_rel(rel)
    _CREATED_FILES.clear()


# ---- 辅助（对齐 test_orders.py 约定）----


def _sess(t):
    return t.session if hasattr(t, "session") else t


def _mk_user(target, *, username="alice", email=None, admin=False, active=True):
    db = _sess(target)
    u = User(
        username=username, email=email if email is not None else f"{username}@x.com",
        password_hash=security.hash_password("passw0rd"),
        is_admin=admin, is_active=active,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


FILE_BYTES = b"FILECONTENT" * 81 + b"END" * 3  # 恰好 900B（11*81+9），便于 Range 验证


def _mk_product(target, *, title="t", price=10000, listed=True,
                file_name="课件-第3章.zip"):
    """带真实资源文件（中文文件名）的上架商品；写真实字节到 downloads/。"""
    db = _sess(target)
    name = f"dltest_{time.time_ns()}.zip"
    full = storage.root("downloads") / name
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(FILE_BYTES)
    rel = f"downloads/{name}"
    _CREATED_FILES.append(rel)
    p = Product(
        title=title, category="other", tags=[],
        price_cents=price, is_listed=listed,
        file_url=rel, file_size=full.stat().st_size, file_name=file_name,
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


def _auth(u: User):
    return {"Authorization": f"Bearer {security.create_access_token(u.id)}"}


def _get_order(db, order_no):
    return db.execute(select(Order).where(Order.order_no == order_no)).scalar_one()


def _mk_paid_order(client, *, username="alice", price=10000):
    """造一笔已核销(paid)订单，返回 (order_no, user, product, admin)。"""
    from app.services import order_service

    u = _mk_user(client, username=username)
    p = _mk_product(client, price=price)
    no = client.post(f"{API}/orders", json={"product_id": p.id},
                     headers=_auth(u)).json()["order_no"]
    admin = _mk_user(client, username=f"adm_{username}", admin=True)
    order_service.confirm_order(_sess(client), admin_id=admin.id, ip="10.0.0.1",
                                order_no=no, pay_channel="wechat", note=None)
    return no, u, p, admin


def _clear_quota(order_id: int) -> None:
    get_redis().delete(f"dl:quota:{order_id}")


def _clear_quota_for(db, order_no: str) -> None:
    """按 order_no 清 Redis 配额 key（测试隔离，避免跨用例计数串扰）。"""
    _clear_quota(_get_order(db, order_no).id)


# ---- 1. 校验链：未支付 403 / 撤销 403 / 他人 404 ----

def test_download_requires_paid(client, db):
    u = _mk_user(client, username="alice")
    p = _mk_product(client, price=10000)
    no = client.post(f"{API}/orders", json={"product_id": p.id},
                     headers=_auth(u)).json()["order_no"]
    # 未支付（pending）→ 403 ORDER_NOT_PAID
    r = client.get(f"{API}/orders/{no}/download", headers=_auth(u))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "ORDER_NOT_PAID"


def test_download_other_user_404(client, db):
    """他人订单（或不存在）→ 404 防探测。"""
    no, u, p, _ = _mk_paid_order(client, username="alice")
    stranger = _mk_user(client, username="bob")
    r = client.get(f"{API}/orders/{no}/download", headers=_auth(stranger))
    assert r.status_code == 404
    # 不存在的订单号
    assert client.get(f"{API}/orders/RM000000000000000A/download",
                      headers=_auth(u)).status_code == 404


def test_download_requires_login(client, db):
    no, u, p, _ = _mk_paid_order(client, username="alice")
    assert client.get(f"{API}/orders/{no}/download").status_code == 401


def test_download_revoked_403(client, db):
    """撤销后下载 → 403（09 §2：撤销后 403）。"""
    from app.services import order_service

    no, u, p, admin = _mk_paid_order(client, username="alice")
    order_service.revoke_order(db, admin_id=admin.id, ip="10.0.0.1",
                               order_no=no, reason="错核销处理")
    r = client.get(f"{API}/orders/{no}/download", headers=_auth(u))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ORDER_NOT_PAID"


# ---- 2. 正常签发 → 302 → /files 直出 + Range + 中文文件名 + 留痕 ----

def test_download_issue_302_and_serve(client, db):
    no, u, p, _ = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    r = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                   follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert loc.startswith(f"{API}/files/")
    # 直出（跟随）：200，attachment，中文文件名 RFC5987，完整内容
    body = client.get(loc, follow_redirects=False)
    assert body.status_code == 200, body.text
    cd = body.headers["content-disposition"]
    assert "attachment" in cd
    from urllib.parse import unquote, quote
    assert unquote(cd.split("filename*=UTF-8''")[1]) == "课件-第3章.zip"
    assert body.content == FILE_BYTES
    # 留痕：该订单 1 条 download_logs。TestClient 客户端 host="testclient"（非法 IP）
    # → _sanitize_ip 归一为 None 存库，验证不触发 INET 插入 500（见 test_sanitize_ip）。
    oid = _get_order(db, no).id
    logs = db.execute(select(DownloadLog).where(DownloadLog.order_id == oid)).scalars().all()
    assert len(logs) == 1
    assert logs[0].ip is None
    assert logs[0].user_agent is not None


def test_download_range_resume(client, db):
    """Range 断点续传：curl -r 等价 → 206 + content-range（09 §2）。"""
    no, u, p, _ = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    loc = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                     follow_redirects=False).headers["location"]
    r = client.get(loc, headers={"Range": "bytes=0-89"}, follow_redirects=False)
    assert r.status_code == 206, r.text
    assert r.headers["content-range"] == "bytes 0-89/900"
    assert len(r.content) == 90
    # 越界 → 416（无有效字节）
    r2 = client.get(loc, headers={"Range": "bytes=900-"}, follow_redirects=False)
    assert r2.status_code == 416, r2.text


# ---- 3. 限流：7 天 50 次，第 51 次 429（文案含剩余窗口）----

def test_download_quota_exceed_51st_429(client, db):
    no, u, p, _ = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    quota = settings.download_quota  # 50
    for i in range(quota):
        r = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                       follow_redirects=False)
        assert r.status_code == 302, f"第 {i+1} 次应 302，实际 {r.status_code}"
    # 第 51 次 → 429 DOWNLOAD_QUOTA_EXCEEDED，文案含剩余窗口
    r = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                   follow_redirects=False)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "DOWNLOAD_QUOTA_EXCEEDED"
    assert "小时" in r.json()["error"]["message"] or "窗口" in r.json()["error"]["message"]
    # 第 51 次被拒 → 不应新增留痕（仍是 50 条）
    oid = _get_order(db, no).id
    assert (
        db.execute(select(DownloadLog).where(DownloadLog.order_id == oid)).scalars().all().__len__() == quota
    )


def test_download_quota_not_counted_on_files_revisit(client, db):
    """短链重复访问 /files/{token} 不计配额（05 §4：配额只在签发时计数）。"""
    no, u, p, _ = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    loc = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                     follow_redirects=False).headers["location"]
    # 同一短链重复直接访问 3 次（模拟大文件重试）→ 均 200，且不增签发计数
    for _ in range(3):
        assert client.get(loc, follow_redirects=False).status_code == 200
    oid = _get_order(db, no).id
    # 仅 1 次签发 → 1 条留痕；再签发 1 次 → 2 条（证明 /files 访问未计数）
    client.get(f"{API}/orders/{no}/download", headers=_auth(u), follow_redirects=False)
    assert (
        db.execute(select(DownloadLog).where(DownloadLog.order_id == oid)).scalars().all().__len__() == 2
    )


# ---- 4. 15min 过期 → 410；篡改 → 403 ----

def test_files_expired_410(client, db):
    no, u, p, _ = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    loc = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                     follow_redirects=False).headers["location"]
    token = loc.split("/files/")[-1]
    oid = _get_order(db, no).id
    # 手工构造一个 exp 已过期的合法签名（复用 secret_file，仅把 exp 改为过去）
    exp = int(time.time()) - 10
    import base64, hashlib, hmac as _hmac
    from app.core.config import settings as _s
    payload = f"file|{oid}|{exp}".encode()
    sig = _hmac.new(_s.secret_file.encode(), payload, hashlib.sha256).hexdigest()
    tok = base64.urlsafe_b64encode(payload + b"|" + sig.encode()).decode().rstrip("=")
    r = client.get(f"{API}/files/{tok}", follow_redirects=False)
    assert r.status_code == 410, r.text
    assert r.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_files_tampered_403(client, db):
    no, u, p, _ = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    loc = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                     follow_redirects=False).headers["location"]
    token = loc.split("/files/")[-1]
    # 改 1 字符 → 验签失败 403 TOKEN_INVALID
    bad = ("A" if token[0] != "A" else "B") + token[1:]
    r = client.get(f"{API}/files/{bad}", follow_redirects=False)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "TOKEN_INVALID"


# ---- 5. 消费前复核 paid：签发后撤销 → 旧短链 403 ----

def test_files_recheck_revoked_after_issue(client, db):
    """签发 302 拿到短链后，管理员撤销 → 再访问该短链 → 403 ORDER_NOT_PAID（05 §1 防撤销窗口）。"""
    from app.services import order_service

    no, u, p, admin = _mk_paid_order(client, username="alice")
    _clear_quota_for(db, no)
    loc = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                     follow_redirects=False).headers["location"]
    # 撤销
    order_service.revoke_order(db, admin_id=admin.id, ip="10.0.0.1",
                               order_no=no, reason="错核销处理")
    r = client.get(loc, follow_redirects=False)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "ORDER_NOT_PAID"


# ---- 6. 降级：Redis 不可用 → 查 download_logs 兜底（DB 可用则放行）----

def test_quota_fallback_db_when_redis_down(client, db, monkeypatch):
    """Redis 挂 → 用 download_logs 近 7 天 COUNT 兜底；达到配额 → 429（05 §4 降级）。"""
    import app.services.download_service as ds

    no, u, p, _ = _mk_paid_order(client, username="alice")
    oid = _get_order(db, no).id
    _clear_quota_for(db, no)

    class _Dead:
        def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(ds, "get_redis", lambda: _Dead())
    # 造满 50 条留痕（近 7 天）→ 下次签发应 429（DB 兜底计数）
    from datetime import datetime, timezone
    for _ in range(settings.download_quota):
        db.add(DownloadLog(order_id=oid, ip="1.2.3.4",
                           created_at=datetime.now(timezone.utc)))
    db.commit()
    r = client.get(f"{API}/orders/{no}/download", headers=_auth(u),
                   follow_redirects=False)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "DOWNLOAD_QUOTA_EXCEEDED"


# ---- 7. IP 归一化（INET 列防御）----

def test_sanitize_ip():
    from app.services.download_service import _sanitize_ip

    assert _sanitize_ip("1.2.3.4") == "1.2.3.4"
    assert _sanitize_ip("2001:db8::1") == "2001:db8::1"
    assert _sanitize_ip("::ffff:1.2.3.4") == "1.2.3.4"  # IPv4-mapped → IPv4
    # 非法值（测试客户端 / 代理垃圾）→ None，避免 INET 插入 500
    assert _sanitize_ip("testclient") is None
    assert _sanitize_ip("") is None
    assert _sanitize_ip(None) is None
    assert _sanitize_ip("not-an-ip") is None


# ---- 8. P4 并发（09 §1 P4-3 / §3：线程池 + 真实连接池，恰好 N 成功，禁止模糊断言）----


def test_concurrent_60_issue_exactly_50_ok(client, db):
    """同订单 60 并发下载签发 → 恰好 50 成功（拿到短链）、10 个 429（配额内精确对账）。

    竞争点在 Redis INCR（单线程计数器，n=1..60 无丢失更新）；
    每线程独立 Session 但共用 engine 连接池（09 §3 要求，不 mock DB）。
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.core.exceptions import BizError
    from app.db.base import SessionLocal
    from app.services import download_service

    no, u, p, _ = _mk_paid_order(client, username="alice")
    oid = _get_order(db, no).id
    _clear_quota_for(db, no)

    def _one(_: int) -> str:
        s = SessionLocal()
        try:
            download_service.issue(
                s, user_id=u.id, order_no=no, ip="10.0.0.1", user_agent="p4-conc"
            )
            return "ok"
        except BizError as e:
            return f"err:{e.status}"
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=60) as ex:
        results = list(ex.map(_one, range(60)))

    ok = results.count("ok")
    limited = results.count("err:429")
    assert ok == 50, f"恰好 50 成功，实际 {ok}：{sorted(set(results))}"
    assert limited == 10, f"恰好 10 个 429，实际 {limited}：{sorted(set(results))}"
    # 留痕与成功签发一一对应（恰好 50 条）
    db.expire_all()
    n_logs = db.execute(
        select(DownloadLog).where(DownloadLog.order_id == oid)
    ).scalars().all().__len__()
    assert n_logs == 50, n_logs
