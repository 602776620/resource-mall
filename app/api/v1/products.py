"""商品路由（04 §4 前台 / §6 后台 / §7 预览短链）。"""
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.core import signed_link, storage
from app.core.deps import get_db, require_admin
from app.core.exceptions import BizError
from app.db.models import Product, User
from app.schemas.product import (
    CATEGORIES,
    CategoryOut,
    Paged,
    ProductDetailOut,
    ProductOut,
)
from app.services import product_service

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ---- 前台（04 §4，无鉴权）----


@router.get("/products", response_model=Paged)
def list_products(
    request: Request,
    category: str | None = Query(None),
    keyword: str | None = Query(None),
    sort: str = Query("new", pattern="^(new|price_asc|price_desc)$"),
    price_min_cents: int | None = Query(None, ge=0),
    price_max_cents: int | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Paged:
    items, total = product_service.list_products(
        db,
        category=category,
        keyword=keyword,
        sort=sort,
        price_min_cents=price_min_cents,
        price_max_cents=price_max_cents,
        page=page,
        page_size=page_size,
    )
    return Paged(items=[i.model_dump() for i in items], total=total, page=page, page_size=page_size)


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def product_detail(product_id: int, db: Session = Depends(get_db)) -> ProductDetailOut:
    return product_service.get_public_product_out(db, product_id)


@router.get("/products/{product_id}/preview")
def product_preview(product_id: int, db: Session = Depends(get_db)) -> dict:
    return {"items": product_service.preview_urls(db, product_id)}


@router.get("/categories", response_model=list[CategoryOut])
def categories() -> list[CategoryOut]:
    return [CategoryOut(key=k, label=v) for k, v in CATEGORIES]


# ---- 预览媒体短链（04 §7，无鉴权，验签 → 前缀白名单 → 直出）----

_MEDIA_PREFIXES = ("uploads/covers/", "uploads/preview/")


@router.get("/media/{token}")
async def media_token(request: Request, token: str, db: Session = Depends(get_db)):
    subject, _exp = signed_link.verify(token)
    product_id, relpath = signed_link.parse_media_subject(subject)
    if not relpath.startswith(_MEDIA_PREFIXES):
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    p = db.get(Product, product_id)
    if p is None or not p.is_listed:
        # 06 §1 红线 3：商品已下架/删除 → 短链失效（410 更贴切，统一走 404 防探测）
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    path = storage.resolve_for_read(relpath, ("uploads",))
    return _serve(path, cache=True)


def _serve(path, *, cache: bool, as_attachment: bool = False, filename: str | None = None):
    from starlette.responses import FileResponse

    headers = {}
    if cache:
        # 04 §7：图片直出带短缓存
        headers["Cache-Control"] = "private, max-age=600"
    if as_attachment:
        from urllib.parse import quote

        headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote(filename or path.name)}"
        )
    return FileResponse(path, headers=headers or None)


# ---- 后台（04 §6，需管理员；06 §1 红线 1：所有 /admin/* 统一 require_admin）----

admin_router = APIRouter(dependencies=[Depends(require_admin)])


async def _persist(
    request: Request,
    file: UploadFile | None,
    *,
    kind: str,
    sub: str,
    max_bytes: int,
    exts: set[str],
) -> tuple[str, int, str] | None:
    """读 UploadFile → storage 校验/重命名 → 落盘。返回 (relpath, size, orig_name)。"""
    if file is None:
        return None
    body = await file.read()
    size = len(body)
    relpath = storage.save_upload(kind, sub, file.filename or "", size, max_bytes, exts)
    full = storage.resolve_abs(relpath)  # 相对路径 → 绝对写入位置（已校验在目标目录内）
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(body)
    return relpath, size, file.filename or ""


async def _persist_resource(request: Request, file: UploadFile | None):
    """资源文件：扩展名白名单 + MIME 兜底（05 §8）+ ≤2GB + uuid 重命名。"""
    if file is None:
        return None
    storage.check_resource_mime(file.content_type)
    return await _persist(
        request, file, kind="downloads", sub="",
        max_bytes=storage.MAX_RESOURCE_BYTES, exts=storage.RESOURCE_EXTS,
    )


async def _persist_preview(
    request: Request,
    images: list[UploadFile] | None,
    samples: list[UploadFile] | None,
) -> list[dict]:
    """预览媒体（05 §8）：preview_images ≤9 张 ≤5MB（图白名单）+ preview_files ≤3 个 ≤20MB。

    任一文件失败 → 已落盘部分物理回滚后向上抛。
    """
    images = images or []
    samples = samples or []
    if len(images) > 9:
        raise BizError("预览图最多 9 张", status=422, code="VALIDATION")
    if len(samples) > 3:
        raise BizError("预览样本文件最多 3 个", status=422, code="VALIDATION")

    media: list[dict] = []
    persisted: list[str] = []

    def _cleanup() -> None:
        for rel in persisted:
            storage.delete_rel(rel)
        persisted.clear()

    try:
        for f in images:
            item = await _persist(
                request, f, kind="uploads", sub="preview",
                max_bytes=storage.MAX_PREVIEW_IMAGE_BYTES, exts=storage.PREVIEW_IMAGE_EXTS,
            )
            if item is None:
                continue
            rel, _sz, orig = item
            persisted.append(rel)
            media.append({"kind": "image", "url": rel, "name": orig})
        for f in samples:
            item = await _persist(
                request, f, kind="uploads", sub="preview",
                max_bytes=storage.MAX_PREVIEW_FILE_BYTES, exts=storage.PREVIEW_FILE_EXTS,
            )
            if item is None:
                continue
            rel, _sz, orig = item
            persisted.append(rel)
            media.append({"kind": "file", "url": rel, "name": orig})
    except BizError:
        _cleanup()
        raise
    return media


def _parse_form(form: dict, tags: str | None = None) -> dict:
    """multipart 表单字段 → service data dict。校验价格/分类/标签。"""
    data: dict = {}
    if "title" in form:
        title = (form.get("title") or "").strip()
        if not (1 <= len(title) <= 120):
            raise BizError("标题需 1~120 字", status=422, code="VALIDATION")
        data["title"] = title
    if form.get("subtitle") is not None:
        data["subtitle"] = form.get("subtitle")
    if "category" in form:
        if form["category"] not in {k for k, _ in CATEGORIES}:
            raise BizError("分类无效", status=422, code="VALIDATION")
        data["category"] = form["category"]
    if tags is not None:
        # 02 §1：逗号分隔标签串 → 列表（上限 20 个）
        data["tags"] = [t.strip() for t in tags.split(",") if t.strip()][:20]
    if "price_cents" in form:
        pc = form.get("price_cents")
        try:
            pc = int(pc)
        except (TypeError, ValueError):
            raise BizError("价格无效", status=422, code="VALIDATION")
        if pc <= 0:
            raise BizError("价格必须大于 0", status=422, code="VALIDATION")
        data["price_cents"] = pc
    if form.get("original_price_cents") not in (None, ""):
        op = form.get("original_price_cents")
        if op not in (None, ""):
            try:
                op = int(op)
            except (TypeError, ValueError):
                raise BizError("原价无效", status=422, code="VALIDATION")
            data["original_price_cents"] = op
    if form.get("description") is not None:
        data["description"] = form.get("description")
    if "listed" in form:
        v = form.get("listed")
        data["listed"] = str(v).lower() in ("1", "true", "yes")
    return data


@admin_router.get("/products", response_model=Paged)
def admin_list(
    keyword: str | None = Query(None),
    listed: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Paged:
    items, total = product_service.admin_list_products(
        db, keyword=keyword, listed=listed, page=page, page_size=page_size
    )
    return Paged(items=[i.model_dump() for i in items], total=total, page=page, page_size=page_size)


@admin_router.get("/products/{product_id}", response_model=ProductDetailOut)
def admin_detail(product_id: int, db: Session = Depends(get_db)) -> ProductDetailOut:
    return product_service.get_admin_product_out(db, product_id)


@admin_router.post("/products", status_code=201)
async def admin_create(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
    title: str | None = Form(None),
    subtitle: str | None = Form(None),
    category: str | None = Form(None),
    tags: str | None = Form(None),
    price_cents: int | None = Form(None),
    original_price_cents: int | None = Form(None),
    description: str | None = Form(None),
    listed: str = Form("false"),
    cover: UploadFile | None = File(None),
    preview_images: list[UploadFile] | None = File(None),
    preview_files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
):
    # 05 §8：资源文件 ≤ 2GB（MIME/扩展名白名单在 storage.save_upload）
    saved: dict = {}
    try:
        saved["cover"] = await _persist(
            request, cover, kind="uploads", sub="covers",
            max_bytes=storage.MAX_COVER_BYTES, exts=storage.COVER_EXTS,
        )
        saved["preview"] = await _persist_preview(request, preview_images, preview_files)
        saved["resource"] = await _persist_resource(request, file)
    except BizError:
        for rels in (saved.get("cover"), saved.get("resource")):
            if rels:
                storage.delete_rel(rels[0])
        for m in saved.get("preview", []):
            storage.delete_rel(m.get("url"))
        raise

    form = {
        "title": title, "subtitle": subtitle, "category": category, "tags": tags,
        "price_cents": price_cents, "original_price_cents": original_price_cents,
        "description": description, "listed": listed,
    }
    data = _parse_form(form, tags)
    if "title" not in data or "category" not in data or "price_cents" not in data:
        raise BizError("缺少必填字段 title/category/price_cents", status=422, code="VALIDATION")
    p = product_service.create_admin_product(
        db, admin_id=current.id, ip=_client_ip(request), data=data, saved_files=saved
    )
    return {"product": product_service.product_out(p)}


@admin_router.put("/products/{product_id}")
async def admin_update(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
    title: str | None = Form(None),
    subtitle: str | None = Form(None),
    category: str | None = Form(None),
    tags: str | None = Form(None),
    price_cents: int | None = Form(None),
    original_price_cents: int | None = Form(None),
    description: str | None = Form(None),
    listed: str | None = Form(None),
    cover: UploadFile | None = File(None),
    preview_images: list[UploadFile] | None = File(None),
    preview_files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
):
    saved: dict = {}
    try:
        saved["cover"] = await _persist(
            request, cover, kind="uploads", sub="covers",
            max_bytes=storage.MAX_COVER_BYTES, exts=storage.COVER_EXTS,
        )
        # 缺省=不改：未提供任何预览文件 → 不动 preview_media
        saved["preview"] = (
            await _persist_preview(request, preview_images, preview_files)
            if (preview_images or preview_files)
            else None
        )
        saved["resource"] = await _persist_resource(request, file)
    except BizError:
        for key in ("cover", "resource"):
            if saved.get(key):
                storage.delete_rel(saved[key][0])
        for m in saved.get("preview") or []:
            storage.delete_rel(m.get("url"))
        raise

    form = {
        "title": title, "subtitle": subtitle, "category": category, "tags": tags,
        "price_cents": price_cents, "original_price_cents": original_price_cents,
        "description": description, "listed": listed,
    }
    data = {k: v for k, v in form.items() if v is not None}
    p = product_service.update_admin_product(
        db, admin_id=current.id, ip=_client_ip(request), product_id=product_id,
        data=data, saved_files=saved,
    )
    return {"product": product_service.product_out(p)}


@admin_router.post("/products/{product_id}/list")
def admin_list_it(
    product_id: int, request: Request, db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    p = product_service.set_listed(
        db, admin_id=current.id, ip=_client_ip(request), product_id=product_id, listed=True
    )
    return {"product": product_service.product_out(p)}


@admin_router.post("/products/{product_id}/unlist")
def admin_unlist(
    product_id: int, request: Request, db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    p = product_service.set_listed(
        db, admin_id=current.id, ip=_client_ip(request), product_id=product_id, listed=False
    )
    return {"product": product_service.product_out(p)}


@admin_router.delete("/products/{product_id}", status_code=204)
def admin_delete(
    product_id: int, request: Request, db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    product_service.delete_admin_product(
        db, admin_id=current.id, ip=_client_ip(request), product_id=product_id
    )
    return None
