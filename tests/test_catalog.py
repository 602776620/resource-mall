"""T05 前台浏览（09 §2-T05）：筛选组合 / 关键词 / 分页边界。打真实 mall_test 对拍 SQL。"""
import time
from datetime import datetime, timedelta, timezone

from app.db.models import Product

API = "/api/v1"


def _mk(db, *, title="t", category="other", price=100, listed=True,
        tags=None, created=None, original=None):
    p = Product(
        title=title,
        category=category,
        tags=tags or [],
        price_cents=price,
        original_price_cents=original,
        is_listed=listed,
    )
    if created is not None:
        p.created_at = created
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed(db):
    """造一组可控数据：分类/价格/标签/上架态/创建时间各异。"""
    now = datetime.now(timezone.utc)
    mk = lambda **kw: _mk(db, created=now + timedelta(seconds=kw.pop("_t", 0)), **kw)
    # A：tutorial，价格 9900，tag python，上架
    a = mk(title="Python 入门", category="tutorial", price=9900, tags=["python", "data"], _t=10)
    # B：template，价格 19900，tag python，上架，原价 29900
    b = mk(title="React 模板", category="template", price=19900, original=29900,
           tags=["python", "web"], _t=20)
    # C：material，价格 500，上架
    c = mk(title="素材包", category="material", price=500, tags=["design"], _t=30)
    # D：tutorial，价格 100，上架，标题含「入门」
    d = mk(title="Go 入门", category="tutorial", price=100, tags=["golang"], _t=40)
    # E：未上架（前台不应出现）
    e = mk(title="隐藏教程", category="tutorial", price=9999, listed=False, _t=50)
    return [a, b, c, d, e]


def test_only_listed_visible(client):
    db = client.session
    _seed(db)
    r = client.get(f"{API}/products", params={"page_size": 100})
    assert r.status_code == 200
    titles = {it["title"] for it in r.json()["items"]}
    assert "隐藏教程" not in titles
    assert r.json()["total"] == 4  # E 未上架不计


def test_category_filter(client):
    db = client.session
    _seed(db)
    r = client.get(f"{API}/products", params={"category": "tutorial", "page_size": 100})
    items = r.json()["items"]
    assert {it["title"] for it in items} == {"Python 入门", "Go 入门"}
    assert r.json()["total"] == 2


def test_price_range_and_sort(client):
    db = client.session
    _seed(db)
    # 价格区间 [100, 9900] → A(9900) D(100)；C(500) 也在区间内
    r = client.get(
        f"{API}/products",
        params={"price_min_cents": 100, "price_max_cents": 9900, "sort": "price_asc", "page_size": 100},
    )
    prices = [it["price_cents"] for it in r.json()["items"]]
    assert prices == [100, 500, 9900], prices  # D, C, A 升序
    # price_desc 倒序
    r = client.get(f"{API}/products", params={"sort": "price_desc", "page_size": 100})
    prices = [it["price_cents"] for it in r.json()["items"]]
    assert prices == sorted(prices, reverse=True)
    assert prices[0] == 19900  # B 最贵


def test_keyword_matches_title_or_tag(client):
    db = client.session
    _seed(db)
    # 关键词命中 title（「入门」→ A Python入门 / D Go入门）
    r = client.get(f"{API}/products", params={"keyword": "入门", "page_size": 100})
    titles = {it["title"] for it in r.json()["items"]}
    assert titles == {"Python 入门", "Go 入门"}
    # 关键词命中 tag（python → A、B；title 不含 python）
    r = client.get(f"{API}/products", params={"keyword": "python", "page_size": 100})
    titles = {it["title"] for it in r.json()["items"]}
    assert titles == {"Python 入门", "React 模板"}
    # 大小写不敏感（PYTHON）
    r = client.get(f"{API}/products", params={"keyword": "PYTHON", "page_size": 100})
    assert r.json()["total"] == 2


def test_keyword_case_insensitive_sql(client):
    db = client.session
    _seed(db)
    # ILIKE：「入门」中文不受大小写影响；英文 tag 大小写混用
    r = client.get(f"{API}/products", params={"keyword": "pYtHoN", "page_size": 100})
    assert r.json()["total"] == 2


def test_combined_filters(client):
    db = client.session
    _seed(db)
    # category=tutorial + price<=9900 + keyword 入门 → 仅 A（D 无「入门」？有；A 有）
    r = client.get(
        f"{API}/products",
        params={
            "category": "tutorial",
            "price_max_cents": 9900,
            "keyword": "入门",
            "sort": "price_asc",
            "page_size": 100,
        },
    )
    titles = {it["title"] for it in r.json()["items"]}
    # A(9900,入门) 与 D(100,入门) 都满足 → 两者
    assert titles == {"Python 入门", "Go 入门"}


def test_pagination_bounds(client):
    db = client.session
    _seed(db)  # 4 条上架
    # 末页：page_size=2, page=2 → 第 3-4 条
    r = client.get(f"{API}/products", params={"page": 2, "page_size": 2})
    body = r.json()
    assert body["total"] == 4
    assert body["page"] == 2 and body["page_size"] == 2
    assert len(body["items"]) == 2
    # 超页：page=10 → 空 items，total 仍 4
    r = client.get(f"{API}/products", params={"page": 10, "page_size": 2})
    body = r.json()
    assert body["items"] == [] and body["total"] == 4
    # page_size 上限 100（>100 → 422）
    r = client.get(f"{API}/products", params={"page_size": 101})
    assert r.status_code == 422
    # page<1 → 422
    r = client.get(f"{API}/products", params={"page": 0})
    assert r.status_code == 422


def test_detail_unlisted_404(client):
    db = client.session
    e = _seed(db)[4]  # 未上架
    r = client.get(f"{API}/products/{e.id}")
    assert r.status_code == 404
    # 不存在
    assert client.get(f"{API}/products/99999").status_code == 404


def test_detail_listed_returns_description(client):
    db = client.session
    a = _seed(db)[0]
    a.description = "<p>desc</p><script>bad</script>"
    db.commit()
    r = client.get(f"{API}/products/{a.id}")
    assert r.status_code == 200
    body = r.json()
    assert "description" in body
    assert body["id"] == a.id


def test_detail_preview_signed_urls_valid(client):
    """09 T05-4：详情页预览媒体返回签名短链且 10min 内可验证（前端 /media 短链可下载）。"""
    from app.core import signed_link, storage
    from pathlib import Path

    rel = "uploads/preview/catalog_sample.png"
    full = Path(storage.root("uploads")) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(b"PNGSAMPLE")
    try:
        db = client.session
        a = _seed(db)[0]
        a.preview_media = [
            {"kind": "image", "url": rel},
            {"kind": "file", "url": rel, "name": "样本.png"},
        ]
        db.commit()
        r = client.get(f"{API}/products/{a.id}")
        assert r.status_code == 200
        items = r.json()["preview_media"]
        assert len(items) == 2
        for it in items:
            assert it["url"].startswith("/media/")
            # 短链可解析、绑定该商品、未过期
            subject, exp = signed_link.verify(it["url"].rsplit("/", 1)[1])
            pid, rp = signed_link.parse_media_subject(subject)
            assert pid == a.id and rp == rel
            assert exp > time.time()
        # 短链真实直出 200（04 §7）
        token = items[0]["url"].rsplit("/", 1)[1]
        r2 = client.get(f"{API}/media/{token}")
        assert r2.status_code == 200
        assert r2.content == b"PNGSAMPLE"
    finally:
        storage.delete_rel(rel)
