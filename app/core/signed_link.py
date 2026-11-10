"""签名短链（04 §5/§7 / 06 §3）：HMAC-SHA256，token = base64url(subject | exp_epoch | hmac_hex)。

- /media/{token}：subject = "media|{product_id}|{relpath}"，exp = now + 10min。
- /files/{token}（T06）：subject = "file|{order_id}"，exp = now + 15min。
- 验签失败 → 403 TOKEN_INVALID；过期 → 410 TOKEN_EXPIRED。
"""
import base64
import hashlib
import hmac
import time

from app.core.config import settings
from app.core.exceptions import BizError

MEDIA_TTL = 600  # 04 §7：10 分钟
FILE_TTL = 900  # 04 §5：15 分钟


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(token: str) -> bytes:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + pad)


def _sign(payload: bytes) -> str:
    return hmac.new(settings.secret_file.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _make(subject: str, ttl: int) -> str:
    exp = int(time.time()) + ttl
    payload = f"{subject}|{exp}".encode("utf-8")
    return _b64e(payload + b"|" + _sign(payload).encode("ascii"))


def sign_media(product_id: int, relpath: str) -> str:
    """media 相对路径 → 签名 url path（/media/<token>）。"""
    return f"/media/{_make(f'media|{product_id}|{relpath}', MEDIA_TTL)}"


def sign_file(order_id: int) -> str:
    return f"/files/{_make(f'file|{order_id}', FILE_TTL)}"


def verify(token: str) -> tuple[str, int]:
    """验签 + 过期检查。返回 (subject, exp)。失败抛 BizError（403/410）。

    blob = subject | exp | sig（subject 本身含 |，如 'media|id|rel'），
    故按「最后一个 | 切 sig、再在签名段内最后一个 | 切 exp」还原。
    """
    try:
        raw = _b64d(token)
        signed_payload, sig = raw.rsplit(b"|", 1)  # signed_payload = subject|exp
        subject, exp_b = signed_payload.rsplit(b"|", 1)
        exp = int(exp_b)
    except (ValueError, TypeError):
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    if not hmac.compare_digest(_sign(signed_payload), sig.decode("ascii")):
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    if exp < time.time():
        raise BizError("链接已过期", status=410, code="TOKEN_EXPIRED")
    return subject.decode("utf-8"), exp


def parse_media_subject(subject: str) -> tuple[int, str]:
    """'media|{product_id}|{relpath}' → (product_id, relpath)。格式错 → 403。"""
    parts = subject.split("|", 2)
    if len(parts) != 3 or parts[0] != "media":
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        raise BizError("签名无效", status=403, code="TOKEN_INVALID")
