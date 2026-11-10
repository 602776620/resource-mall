"""T04 资源管理（09 §2-T04）。打真实测试库 mall_test，逐条验收。

覆盖：上传超限/非白名单 422/FILE_TOO_LARGE、uuid 重命名、路径注入 400 未落盘、
上架无 file 422、下架后前台 404、有订单商品删除 409 HAS_ORDERS、
预览媒体只返回签名 url（无直连路径泄漏）、越权 401/403、审计留痕。
"""
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core import signed_link, storage
from app.core import security
from app.db.models import AuditLog, Order, Product, User

API = "/api/v1"

# ---- 辅助（与 test_auth.py 同风格）----


def _sess(target):
    return target.session if hasattr(target, "session") else target


def _mk_user(target, *, username="alice", email=None, admin=False, active=True):
    db = _sess(target)
    if email is None:
        email = f"{username}@x.com"
    u = User(username=username, email=email, is_admin=admin, is_active=active)
    u.password_hash = security.hash_password("passw0rd")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(client, account, password="passw0rd") -> dict:
    r = client.post(f"{API}/auth/login", json={"account": account, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["tokens"]


def _admin_headers(client) -> dict:
    """默认管理员用户名 alice（_mk_user 默认值）。"""
    tokens = _login(client, "alice")
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _mk_product(
    db,
    *,
    title="测试资源",
    category="tutorial",
    price_cents=9900,
    is_listed=True,
    cover=None,
    preview=None,
    file_url=None,
    file_name=None,
    file_size=None,
    tags=None,
) -> Product:
    p = Product(
        title=title,
        category=category,
        tags=tags or [],
        price_cents=price_cents,
        cover_image=cover,
        preview_media=preview or [],
        is_listed=is_listed,
        file_url=file_url,
        file_name=file_name,
        file_size=file_size,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _abs(relpath: str) -> str:
    base = storage.root("downloads") if relpath.startswith("downloads") else storage.root("uploads")
    return str(base / relpath)


def _write_media(relpath: str, content: bytes = b"IMGDATA") -> str:
    """把内容写到 uploads/downloads 真实目录，返回相对路径（供存库）。"""
    full = Path(_abs(relpath))
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)
    return relpath


def _clean_rel(relpath: str | None) -> None:
    if relpath:
        storage.delete_rel(relpath)


def _admin_create(client, headers, **files) -> dict:
    """构造 multipart 创建请求；files: 文件名 → (bytes, filename, content_type)。"""
    form = {
        "title": "API 创建",
        "category": "template",
        "price_cents": "5000",
        "tags": "a,b",
    }
    return client.post(f"{API}/admin/products", headers=headers, data=form, files=files)


# ---- 越权矩阵（06 §1）----


def test_admin_requires_login(client):
    r = client.get(f"{API}/admin/products")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_admin_forbidden_for_normal_user(client):
    _mk_user(client, username="norm")
    tokens = _login(client, "norm")
    r = client.get(
        f"{API}/admin/products",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_admin_product_create_forbidden(client):
    _mk_user(client, username="norm2")
    tokens = _login(client, "norm2")
    r = client.post(
        f"{API}/admin/products",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        data={"title": "x", "category": "other", "price_cents": "100"},
    )
    assert r.status_code == 403


# ---- 上传校验（09 T04）----


def test_upload_non_whitelist_type_422(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    # .exe 不在资源文件白名单
    r = _admin_create(client, h, file=(("evil.exe", b"MZ..." * 10, "application/octet-stream")))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION"
    # 文件未落盘
    assert not any(f.endswith(".exe") for f in _walk(storage.root("downloads")))


def test_resource_mime_deny(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    # 扩展名 .zip 在白名单，但 content_type 声明可执行 → MIME 兜底 422（05 §8 双校验）
    content = b"MIME-DENY-MARKER" + os.urandom(8)  # 唯一内容，避免误配其他测试遗留文件
    r = _admin_create(client, h, file=(("pkg.zip", content, "application/x-msdownload")))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION"
    # 未落盘：check 在 save_upload 之前，downloads 下不可能出现该唯一内容
    for path in _walk(storage.root("downloads")):
        if os.path.isfile(path):
            assert open(path, "rb").read() != content


def test_upload_too_large_file_400(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    # 预览样本 ≤20MB；传 21MB（用 bytes 精确）
    big = b"x" * (21 * 1024 * 1024)
    r = _admin_create(client, h, preview_files=(("big.png", big, "image/png")))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FILE_TOO_LARGE"
    # 失败回滚：无孤立 preview 文件
    assert list(_walk(storage.root("uploads") / "preview")) == []


def test_upload_path_injection_400_no_persist(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    # 原始文件名带 ../../x → 400 且未落盘
    r = _admin_create(
        client, h,
        file=(("..\\..\\x.zip", b"zz", "application/zip")),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"
    # 目标目录外无 x.zip；downloads 根仅可能合法文件
    assert not (storage.root("downloads")).joinpath("..").resolve().is_file()
    for p in _walk(storage.root("downloads")):
        assert "x.zip" not in p


def test_preview_count_limit(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    imgs = [
        (f"i{k}.png", (b"\x89PNG" + b"0" * 32, "image/png")) for k in range(10)
    ]
    r = _admin_create(client, h, **{f"preview_images[{i}]": v for i, v in enumerate(imgs)})
    # 10 张 > 9 → 422（字段名未解析为列表时亦不应 500）
    assert r.status_code in (400, 422)


def test_filename_renamed_uuid(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    r = _admin_create(
        client, h,
        file=(("original name.zip", b"PK\x03\x04" + b"0" * 16, "application/zip")),
    )
    assert r.status_code == 201, r.text
    body = r.json()["product"]
    pid = body["id"]
    # file_name 保留原名（展示）
    assert body["file_name"] == "original name.zip"
    # 落盘文件名是 uuid.hex + 扩展名
    db = _sess(client)
    p = db.get(Product, pid)
    assert p.file_url and p.file_url.startswith("downloads/")
    base = os.path.basename(p.file_url)
    stem, ext = os.path.splitext(base)
    assert ext == ".zip"
    int(stem, 16)  # 合法 uuid.hex
    assert stem != "original name"
    _clean_rel(p.file_url)


# ---- 上架/下架 ----


def test_listed_without_file_422(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    r = client.post(
        f"{API}/admin/products",
        headers=h,
        data={"title": "no file", "category": "other", "price_cents": "100", "listed": "true"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION"


def test_unlisted_product_404_public(client):
    db = _sess(client)
    p = _mk_product(db, title="未上架", is_listed=False)
    r = client.get(f"{API}/products/{p.id}")
    assert r.status_code == 404
    r = client.get(f"{API}/products?keyword=未上架")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_unlist_then_404(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    db = _sess(client)
    p = _mk_product(db, is_listed=True, title="要下架的")
    assert client.get(f"{API}/products/{p.id}").status_code == 200
    r = client.post(f"{API}/admin/products/{p.id}/unlist", headers=h)
    assert r.status_code == 200
    assert client.get(f"{API}/products/{p.id}").status_code == 404
    # 审计留痕
    logs = db.query(AuditLog).filter_by(action="product.unlist", target_id=p.id).all()
    assert len(logs) == 1 and logs[0].admin_id is not None


# ---- 删除守卫（09 T04）----


def _mk_order(db, product: Product, user: User) -> Order:
    o = Order(
        order_no=f"RM{int(time.time() * 1000)}" + "ABC123",
        user_id=user.id,
        product_id=product.id,
        product_title_snapshot=product.title,
        amount_cents=product.price_cents,
        original_cents=product.price_cents,
        expire_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_delete_product_with_orders_409(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    _mk_user(client, username="buyer")
    db = _sess(client)
    p = _mk_product(db, is_listed=True)
    buyer = db.query(User).filter_by(username="buyer").one()
    _mk_order(db, p, buyer)
    r = client.delete(f"{API}/admin/products/{p.id}", headers=h)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "HAS_ORDERS"
    # 仍可访问（未被删）；用 select 回查避开 identity map 缓存
    assert db.query(Product).filter_by(id=p.id).first() is not None


def test_delete_product_no_orders_removes_files(client):
    _mk_user(client, admin=True)
    h = _admin_headers(client)
    db = _sess(client)
    rel = _write_media("downloads/del.zip")
    cover = _write_media("uploads/covers/del.jpg")
    p = _mk_product(db, is_listed=True, file_url=rel, cover=cover)
    r = client.delete(f"{API}/admin/products/{p.id}", headers=h)
    assert r.status_code == 204, r.text
    # select 回查（返回 None 表示真删了），避开 identity map 缓存
    assert db.query(Product).filter_by(id=p.id).first() is None
    assert not os.path.exists(_abs(rel))
    assert not os.path.exists(_abs(cover))
    # 审计留痕
    assert db.query(AuditLog).filter_by(action="product.delete", target_id=p.id).count() == 1


# ---- 预览媒体签名（09 T04：无直连路径泄漏）----


def test_preview_returns_signed_urls_only(client):
    db = _sess(client)
    rel1 = _write_media("uploads/preview/pv1.png")
    rel2 = _write_media("uploads/preview/pv2.pdf")
    p = _mk_product(
        db,
        is_listed=True,
        preview=[
            {"kind": "image", "url": "uploads/preview/pv1.png"},
            {"kind": "file", "url": "uploads/preview/pv2.pdf", "name": "样本.pdf"},
        ],
    )
    try:
        r = client.get(f"{API}/products/{p.id}/preview")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        for it in items:
            url = it["url"]
            assert url.startswith("/api/v1/media/") or url.startswith("/media/")
            assert "uploads/preview" not in url  # 不泄漏直连路径
            # 短链可解析且有效
            subject, exp = signed_link.verify(url.split("/")[-1])
            product_id, rel = signed_link.parse_media_subject(subject)
            assert product_id == p.id
    finally:
        _clean_rel("uploads/preview/pv1.png")
        _clean_rel("uploads/preview/pv2.pdf")


def test_media_token_serves_and_rejects(client):
    db = _sess(client)
    rel = _write_media("uploads/preview/serve.png", b"PNGBYTES")  # 相对路径
    p = _mk_product(db, is_listed=True, preview=[{"kind": "image", "url": rel}])
    try:
        # 有效短链 → 200 图片字节
        token = signed_link.sign_media(p.id, rel).split("/")[-1]
        r = client.get(f"{API}/media/{token}")
        assert r.status_code == 200
        assert r.content == b"PNGBYTES"
        # 篡改 1 字符 → 403 TOKEN_INVALID
        bad = _tamper(token)
        r = client.get(f"{API}/media/{bad}")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "TOKEN_INVALID"
        # 过期 → 410 TOKEN_EXPIRED
        token = _expired_token(p.id, rel)
        r = client.get(f"{API}/media/{token}")
        assert r.status_code == 410
        assert r.json()["error"]["code"] == "TOKEN_EXPIRED"
        # 商品下架后短链 → 404
        p.is_listed = False
        db.commit()
        token2 = signed_link.sign_media(p.id, rel).split("/")[-1]
        assert client.get(f"{API}/media/{token2}").status_code == 404
    finally:
        _clean_rel(rel)


def _tamper(token: str) -> str:
    raw = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    return raw


def _expired_token(product_id: int, relpath: str) -> str:
    exp = int(time.time()) - 10
    payload = f"media|{product_id}|{relpath}|{exp}".encode()
    from app.core.config import settings

    sig = hmac.new(settings.secret_file.encode(), payload, hashlib.sha256).hexdigest()
    blob = payload + b"|" + sig.encode()
    return base64.urlsafe_b64encode(blob).decode().rstrip("=")


def _walk(base):
    for root, _dirs, files in os.walk(str(base)):
        for f in files:
            yield os.path.join(root, f)
