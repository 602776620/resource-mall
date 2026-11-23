"""GET /files/{token}：资源文件签名短链直出（04 §5，无需登录）。

消费前复核（05 §1）：验签 → 过期 410 → 复核订单 pay_status='paid'（防签发后撤销窗口）
→ 只允许 downloads/ 前缀（06 §1 红线：downloads/ 不挂静态路由，唯一入口是本端点）。
FileResponse 原生支持 Range（206 断点续传，curl -r 验证）与 attachment 头；
中文文件名用 RFC 5987 filename*（04 §5）。
"""
from starlette.responses import FileResponse
from urllib.parse import quote

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import signed_link, storage
from app.core.deps import get_db
from app.core.exceptions import BizError
from app.db.models import Order, Product

router = APIRouter(tags=["files"])


@router.get("/files/{token}", name="files_download")
async def files_download(token: str, db: Session = Depends(get_db)):
    subject, _exp = signed_link.verify(token)  # 验签 403 / 过期 410
    if not subject.startswith("file|"):
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    try:
        order_id = int(subject.split("|", 1)[1])
    except (ValueError, IndexError):
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")

    # 消费前复核 paid（04 §5）：撤销/取消窗口内访问 → 403 ORDER_NOT_PAID
    o = db.get(Order, order_id)
    if o is None:
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    if o.pay_status != "paid":
        raise BizError("订单未支付或已失效", status=403, code="ORDER_NOT_PAID")

    p = db.get(Product, o.product_id)
    if p is None or not p.file_url:
        raise BizError("订单无资源文件", status=404, code="NOT_FOUND")
    # 只放行 downloads/ 前缀（media 短链误用于本端点 → 403 防探测）
    if not p.file_url.startswith("downloads/"):
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    path = storage.resolve_for_read(p.file_url, ("downloads",))  # 穿越/不存在 → 400/404

    filename = p.file_name or path.name
    headers = {
        # 04 §5：attachment + RFC 5987（中文文件名浏览器正确显示）
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
    }
    return FileResponse(path, media_type="application/octet-stream", headers=headers)
