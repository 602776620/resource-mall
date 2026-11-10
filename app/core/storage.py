"""本地文件存储（05 §8 / 06 §2）：白名单、大小、uuid 重命名、路径穿越防护。

红线：
- 资源文件存 downloads/（不可公开，唯一入口是签名短链）；封面/预览存 uploads/。
- 服务端二次校验扩展名白名单 + 大小；文件名重命名 uuid.hex + 原扩展名。
- 落盘/读取相对路径统一 normpath 后校验仍在目标目录内（06 §2.4），穿越 → 400 且文件未落盘。
"""
import os
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import BizError

# 05 §8 白名单（扩展名小写）
COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PREVIEW_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PREVIEW_FILE_EXTS = {".pdf", ".zip", ".mp4", ".png", ".jpg"}
RESOURCE_EXTS = {".zip", ".rar", ".7z", ".pdf", ".mp4", ".png", ".jpg", ".txt"}

MAX_COVER_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_FILE_BYTES = 20 * 1024 * 1024
# 资源文件 ≤ 2GB（05 §8；settings.max_resource_mb 可覆盖，默认 2048MB）
MAX_RESOURCE_BYTES = 2 * 1024 * 1024 * 1024

# 05 §8 资源文件「扩展名+MIME 双校验」：客户端 content_type 不可信，
# 故用可执行类 MIME 黑名单兜底（扩展名白名单已挡绝大部分，此为第二道）。
# 注：不拒 application/octet-stream（TestClient/多数浏览器对任意文件默认发它，
#     拒掉会误伤合法 .zip/.7z）；只拒可执行程序类。
EXEC_MIME_DENYLIST = {
    "application/x-msdownload",
    "application/vnd.microsoft-exe",
    "application/x-msdos-program",
    "application/x-msi",
    "application/x-executable",
}


def check_resource_mime(content_type: str | None) -> None:
    """资源文件 MIME 兜底（05 §8）；命中可执行类 → 422。"""
    if content_type and content_type.split(";")[0].strip().lower() in EXEC_MIME_DENYLIST:
        raise BizError("文件类型不支持", status=422, code="VALIDATION")


def root(kind: str) -> Path:
    base = Path(settings.upload_root) if kind == "uploads" else Path(settings.download_root)
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def _validate_inside(relpath: str, base: Path) -> Path:
    """normpath 后确认仍在 base 内，否则 400（06 §2.4）。"""
    full = (base / relpath).resolve()
    if full != base and not str(full).startswith(str(base) + os.sep):
        raise BizError("非法文件路径", status=400, code="BAD_REQUEST")
    return full


def save_upload(kind: str, sub: str, filename: str, size: int, max_bytes: int, exts: set[str]) -> str:
    """校验 + uuid 重命名 + 落盘，返回相对路径（downloads/x.zip、uploads/covers/x.jpg）。

    kind: 'uploads'|'downloads'；sub: 'covers'|'preview'|''（资源文件在 downloads 根）。
    原始文件名只作展示字段，绝不参与落盘路径（防路径注入/覆盖）。
    """
    # 09 T04：路径注入尝试（`../../x`）→ 400 且文件未落盘
    if filename and ".." in (filename.replace("\\", "/").split("/")):
        raise BizError("非法文件路径", status=400, code="BAD_REQUEST")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in exts:
        raise BizError("文件类型不支持", status=422, code="VALIDATION")
    if size <= 0 or size > max_bytes:
        raise BizError("文件大小超限", status=400, code="FILE_TOO_LARGE")
    name = uuid.uuid4().hex + ext
    # 存库相对路径统一含顶层目录：uploads/covers/x.jpg、uploads/preview/x.jpg、downloads/x.zip
    inner = f"{sub}/{name}" if sub else name
    relpath = f"{kind}/{inner}"
    base = root(kind)
    target = _validate_inside(inner, base)  # 恒在 base 内（uuid 名），兜底防御
    target.parent.mkdir(parents=True, exist_ok=True)
    return relpath


def resolve_abs(relpath: str) -> Path:
    """存库相对路径（含顶层目录）→ 绝对路径（用于写入）。仅允许 uploads/、downloads/ 前缀。"""
    if not relpath or relpath.startswith("/"):
        raise BizError("非法文件路径", status=400, code="BAD_REQUEST")
    norm = os.path.normpath(relpath)
    if ".." in norm.split(os.sep):
        raise BizError("非法文件路径", status=400, code="BAD_REQUEST")
    if not (norm.startswith("uploads") or norm.startswith("downloads")):
        raise BizError("非法文件路径", status=400, code="BAD_REQUEST")
    kind = "downloads" if norm.startswith("downloads") else "uploads"
    inner = norm[len(kind) + 1:]
    return _validate_inside(inner, root(kind))


def resolve_for_read(relpath: str, allowed_prefixes: tuple[str, ...]) -> Path:
    """相对路径 → 绝对路径；前缀白名单 + 穿越校验；不存在 → 404。"""
    if not relpath or relpath.startswith("/"):
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    norm = os.path.normpath(relpath)
    if ".." in norm.split(os.sep):
        raise BizError("非法文件路径", status=400, code="BAD_REQUEST")
    if not any(norm == p or norm.startswith(p + os.sep) for p in allowed_prefixes):
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    kind = "downloads" if norm.startswith("downloads") else "uploads"
    full = _validate_inside(norm, root(kind))
    if not full.is_file():
        raise BizError("资源不存在", status=404, code="NOT_FOUND")
    return full


def delete_rel(relpath: str | None) -> None:
    """物理删除（不存在则忽略）。仅允许 uploads/、downloads/ 前缀（06 红线不外溢）。"""
    if not relpath or relpath.startswith("/"):
        return
    norm = os.path.normpath(relpath)
    if ".." in norm.split(os.sep):
        return
    if not (norm.startswith("uploads") or norm.startswith("downloads")):
        return
    kind = "downloads" if norm.startswith("downloads") else "uploads"
    try:
        full = _validate_inside(norm, root(kind))
        if full.is_file():
            full.unlink()
    except (BizError, OSError):
        pass
