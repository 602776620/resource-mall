"""商品业务逻辑（04 §4/§6 / 06 §2）。依赖注入 db，可单测。"""
import bleach
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from app.core import signed_link, storage
from app.core.exceptions import BizError
from app.services import audit_service
from app.db.models import Order, Product
from app.schemas.product import MediaItem, ProductDetailOut, ProductOut


# 02 §4.5 / 06 §5：description 入库前白名单过滤（其余标签剥离）
ALLOWED_TAGS = ["p", "br", "b", "ul", "ol", "li", "a", "img", "pre", "code", "h1", "h2", "h3"]
ALLOWED_ATTRS = {"a": ["href", "title"], "img": ["src", "alt", "title"], "*": []}


def sanitize_description(raw: str | None) -> str | None:
    if raw is None:
        return None
    return bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


# ---- 序列化 ----

def _media_out(p: Product, signed: bool = False) -> list[MediaItem]:
    """前台：签名短链 url（04 §7 防枚举/防直连）；管理端：原相对路径。"""
    out: list[MediaItem] = []
    for m in p.preview_media or []:
        url = m.get("url", "")
        if signed and url:
            url = signed_link.sign_media(p.id, url)
        out.append(MediaItem(kind=m.get("kind", "image"), url=url, name=m.get("name")))
    return out


def product_out(p: Product, *, signed: bool = False) -> ProductOut:
    return ProductOut(
        id=p.id,
        title=p.title,
        subtitle=p.subtitle,
        category=p.category,
        tags=list(p.tags or []),
        price_cents=p.price_cents,
        original_price_cents=p.original_price_cents,
        cover_image=signed_link.sign_media(p.id, p.cover_image) if (signed and p.cover_image) else p.cover_image,
        preview_media=_media_out(p, signed=signed),
        file_name=p.file_name,
        file_size=p.file_size,
        is_listed=p.is_listed,
        created_at=p.created_at.isoformat() if p.created_at else "",
    )


def product_detail_out(p: Product, *, signed: bool = False) -> ProductDetailOut:
    return ProductDetailOut(
        **product_out(p, signed=signed).model_dump(), description=p.description
    )


# ---- 前台（04 §4）----

def list_products(
    db: Session,
    *,
    category: str | None = None,
    keyword: str | None = None,
    sort: str = "new",
    price_min_cents: int | None = None,
    price_max_cents: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int]:
    """仅 is_listed。keyword 匹配 title 或 tags 任一含词（04 §4 指定 SQL 形态，
    参数化 text()；06 §5：keyword 只进 LIKE 参数）。"""
    q = select(Product).where(Product.is_listed.is_(True))
    if category:
        q = q.where(Product.category == category)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(
            text("products.title ILIKE :kw "
                 "OR EXISTS (SELECT 1 FROM unnest(products.tags) AS t "
                 "WHERE t ILIKE :kw)").bindparams(
                bindparam("kw", value=like)
            )
        )
    if price_min_cents is not None:
        q = q.where(Product.price_cents >= price_min_cents)
    if price_max_cents is not None:
        q = q.where(Product.price_cents <= price_max_cents)

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    if sort == "price_asc":
        q = q.order_by(Product.price_cents.asc(), Product.id.asc())
    elif sort == "price_desc":
        q = q.order_by(Product.price_cents.desc(), Product.id.asc())
    else:  # new（默认）
        q = q.order_by(Product.created_at.desc(), Product.id.desc())
    items = list(db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars())
    return [product_out(p, signed=True) for p in items], total


def get_public_product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    # 06 §1 红线 3：未上架/不存在对外一律 404（防存在性探测）
    if p is None or not p.is_listed:
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    return p


def get_public_product_out(db: Session, product_id: int) -> ProductDetailOut:
    return product_detail_out(get_public_product(db, product_id), signed=True)


def preview_urls(db: Session, product_id: int) -> list[dict[str, Any]]:
    """04 §4/§7：返回 preview_media 各媒体的 10min 签名 url（不泄漏直连路径）。"""
    p = get_public_product(db, product_id)
    out: list[dict[str, Any]] = []
    for m in p.preview_media or []:
        rel = m.get("url") or ""
        if not rel:
            continue
        out.append(
            {
                "kind": m.get("kind", "image"),
                "url": signed_link.sign_media(p.id, rel),
                "name": m.get("name"),
            }
        )
    return out


# ---- 管理端（04 §6）----

def create_admin_product(
    db: Session,
    *,
    admin_id: int,
    ip: str | None,
    data: dict[str, Any],
    saved_files: dict[str, Any],
) -> Product:
    """data 为路由层解析后的 multipart 字段；saved_files 为已落盘文件映射。

    saved_files keys: cover -> (relpath, size, orig_name) | None
                      preview -> [{kind,url,name}]
                      resource -> (relpath, size, orig_name) | None
    """
    listed: bool = bool(data.get("listed", False))
    resource = saved_files.get("resource")
    if listed and resource is None:
        # 04 §6：带 file 才可上架
        raise BizError("上架必须提供资源文件", status=422, code="VALIDATION")

    p = Product(
        title=data["title"],
        subtitle=data.get("subtitle") or None,
        category=data["category"],
        tags=data.get("tags", []),
        price_cents=int(data["price_cents"]),
        original_price_cents=data.get("original_price_cents"),
        cover_image=saved_files["cover"][0] if saved_files.get("cover") else None,
        description=sanitize_description(data.get("description")),
        preview_media=saved_files.get("preview", []),
        is_listed=False,
    )
    if resource:
        relpath, size, orig = resource
        p.file_url = relpath
        p.file_size = size
        p.file_name = orig
        if listed:
            p.is_listed = True
    db.add(p)
    db.flush()
    audit_service.record(
        db, admin_id=admin_id, action="product.create",
        target_type="product", target_id=p.id, ip=ip,
    )
    if p.is_listed:
        audit_service.record(
            db, admin_id=admin_id, action="product.list",
            target_type="product", target_id=p.id, ip=ip,
        )
    db.commit()
    db.refresh(p)
    return p


def update_admin_product(
    db: Session,
    *,
    admin_id: int,
    ip: str | None,
    product_id: int,
    data: dict[str, Any],
    saved_files: dict[str, Any],
) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise BizError("资源不存在", status=404, code="NOT_FOUND")

    # 缺省=不改；文件类：新文件落盘后替换引用，旧文件物理删除
    if "title" in data:
        p.title = data["title"]
    if data.get("subtitle") is not None:
        p.subtitle = data.get("subtitle") or None
    if "category" in data:
        p.category = data["category"]
    if "tags" in data:
        p.tags = data.get("tags", [])
    if "price_cents" in data:
        p.price_cents = int(data["price_cents"])
    if data.get("original_price_cents") is not None:
        p.original_price_cents = data.get("original_price_cents")
    if data.get("description") is not None:
        p.description = sanitize_description(data.get("description"))

    if saved_files.get("cover"):
        old, (rel, _sz, _nm) = p.cover_image, saved_files["cover"]
        p.cover_image = rel
        storage.delete_rel(old)
    if saved_files.get("preview") is not None:
        for m in p.preview_media or []:
            storage.delete_rel(m.get("url"))
        p.preview_media = saved_files["preview"]
    if saved_files.get("resource"):
        old = p.file_url
        rel, size, orig = saved_files["resource"]
        p.file_url, p.file_size, p.file_name = rel, size, orig
        storage.delete_rel(old)
    # 上架校验：请求带 listed=true 时必须已有资源文件
    if bool(data.get("listed", False)) and p.file_url is None:
        raise BizError("上架必须提供资源文件", status=422, code="VALIDATION")

    audit_service.record(
        db, admin_id=admin_id, action="product.update",
        target_type="product", target_id=p.id, ip=ip,
    )
    db.commit()
    db.refresh(p)
    return p


def set_listed(
    db: Session, *, admin_id: int, ip: str | None, product_id: int, listed: bool
) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    if listed and p.file_url is None:
        # 04 §6：上架（file 缺失 422）
        raise BizError("上架必须提供资源文件", status=422, code="VALIDATION")
    p.is_listed = listed
    audit_service.record(
        db, admin_id=admin_id,
        action="product.list" if listed else "product.unlist",
        target_type="product", target_id=p.id, ip=ip,
    )
    db.commit()
    db.refresh(p)
    return p


def delete_admin_product(
    db: Session, *, admin_id: int, ip: str | None, product_id: int
) -> None:
    p = db.get(Product, product_id)
    if p is None:
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    has_orders = db.execute(
        select(Order.id).where(Order.product_id == p.id).limit(1)
    ).first()
    if has_orders is not None:
        # 04 §6：有订单 → 409 HAS_ORDERS（只能下架）
        raise BizError("该商品已有订单，只能下架", status=409, code="HAS_ORDERS")
    for m in p.preview_media or []:
        storage.delete_rel(m.get("url"))
    storage.delete_rel(p.cover_image)
    storage.delete_rel(p.file_url)
    audit_service.record(
        db, admin_id=admin_id, action="product.delete",
        target_type="product", target_id=p.id, ip=ip,
    )
    db.delete(p)
    db.commit()


def admin_list_products(
    db: Session,
    *,
    keyword: str | None = None,
    listed: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    signed: bool = False,
) -> tuple[list[ProductOut], int]:
    q = select(Product)
    if listed is not None:
        q = q.where(Product.is_listed.is_(listed))
    if keyword:
        like = f"%{keyword}%"
        q = q.where(Product.title.ilike(like))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    items = list(
        db.execute(
            q.order_by(Product.created_at.desc(), Product.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    return [product_out(p, signed=signed) for p in items], total


def get_admin_product_out(db: Session, product_id: int) -> ProductDetailOut:
    return product_detail_out(get_admin_product(db, product_id))
