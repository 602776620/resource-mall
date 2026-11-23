"""下载签发与配额（04 §5 / 05 §4 / 06 §1 红线）。

校验链顺序（04 §5，不可调换）：
  1. 本人且存在 → 404 NOT_FOUND（防探测，复用 order_service.get_user_order）
  2. pay_status='paid' → 403 ORDER_NOT_PAID（pending/cancelled/revoked 一律不可下）
  3. Redis 限流 7 天 50 次 → 429 DOWNLOAD_QUOTA_EXCEEDED
  4. 消费前再查一次 pay_status（防「签发后、消费前」核销撤销窗口）
  5. 写 download_logs 留痕（每次签发一条，Redis 丢数据时可重建配额近似值）
  6. 302 → /files/{token}（HMAC 15min，token 由 core/signed_link 生成）

配额实现（05 §4）：key = dl:quota:{order_id}，首次签发 SET 1 EX 604800，之后 INCR；
> 50 → 429，消息含剩余窗口。Redis 不可用 → 降级查 download_logs 近 7 天 COUNT；
DB 也不可用 → 503（文件交付宁缺毋滥，05 §4 降级原则）。
"""
import ipaddress
from datetime import timedelta

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import signed_link
from app.core.config import settings
from app.core.deps import get_redis
from app.core.exceptions import BizError
from app.db.models import DownloadLog
from app.services.order_service import _utcnow, get_user_order

QUOTA_KEY = "dl:quota:{order_id}"
WINDOW_SECONDS = 7 * 24 * 3600  # 05 §4：7 天，TTL 兜底自动清零


class DownloadQuotaError(BizError):
    def __init__(self, remaining: int) -> None:
        super().__init__(
            f"下载次数已用尽（7 天 50 次），请 {remaining} 小时后再试",
            status=429,
            code="DOWNLOAD_QUOTA_EXCEEDED",
        )
        self.remaining = remaining


class QuotaUnavailableError(BizError):
    def __init__(self) -> None:
        super().__init(
            "下载服务暂不可用（配额服务故障，为避免超额已拒绝签发），请稍后重试",
            status=503,
            code="QUOTA_UNAVAILABLE",
        )


def _quota_redis_ok(r) -> bool:
    """探测 Redis 是否可用（区分「Redis 挂」与「DB 挂」。）"""
    try:
        r.ping()
        return True
    except Exception:  # noqa: BLE001 - 限流可降级，降级分支自处理
        return False


def _quota_from_db(db: Session, order_id: int) -> int:
    """降级兜底（05 §4）：download_logs 近 7 天 COUNT。"""
    since = _utcnow() - timedelta(days=settings.download_window_days)
    n = db.execute(
        select(func.count())
        .select_from(DownloadLog)
        .where(DownloadLog.order_id == order_id, DownloadLog.created_at >= since)
    ).scalar_one()
    return n


def _remaining_hours(ttl: int) -> int:
    """429 文案：配额窗口剩余时间（向上取整小时，最小 1）。"""
    return max(1, (ttl + 3599) // 3600)


def _sanitize_ip(value: str | None) -> str | None:
    """归一化客户端 IP 为合法 IPv4/IPv6 字符串；非法（如测试客户端 'testclient'、
    代理塞入的垃圾值）→ None（存 NULL），避免 INET 列插入 500。"""
    if not value:
        return None
    v = value.strip()
    # 候选：原值；若形如 "ip:port"（IPv4）再补一个去掉端口的候选。
    candidates = [v]
    if v.count(":") == 1:
        candidates.append(v.split(":", 1)[0])
    for cand in candidates:
        try:
            addr = ipaddress.ip_address(cand)
        except ValueError:
            continue
        # IPv4 映射 IPv6（::ffff:a.b.c.d）→ 取 IPv4 部分，存库更干净
        return str(addr.ipv4_mapped) if addr.version == 6 and addr.ipv4_mapped else str(addr)
    return None


def _check_and_count(db: Session, order_id: int) -> None:
    """签发前配额检查 + 计数（Redis 优先，DB 兜底，双挂 503）。

    计数发生在「签发 302 之前、复核 paid 之后」由 issue() 编排；
    本函数只做「超限判定 + 自增」，超限抛 DownloadQuotaError。
    """
    quota = settings.download_quota
    key = QUOTA_KEY.format(order_id=order_id)
    try:
        r = get_redis()
    except Exception:  # noqa: BLE001
        r = None
    if r is not None and _quota_redis_ok(r):
        n = r.incr(key)
        if n == 1:
            r.expire(key, WINDOW_SECONDS)  # 首次签发设 7 天窗口（05 §4）
        if n > quota:
            r.decr(key)  # 未实际签发，回退计数
            ttl = r.ttl(key)
            # 剩余窗口（小时，向上取整）：TTL 有效则按剩余 TTL，否则按整窗 7 天
            hours = _remaining_hours(ttl) if ttl and ttl > 0 else _remaining_hours(WINDOW_SECONDS)
            raise DownloadQuotaError(hours)
        return
    # 降级：DB 兜底（05 §4）
    try:
        n = _quota_from_db(db, order_id)
    except SQLAlchemyError as e:
        raise QuotaUnavailableError() from e
    if n >= quota:
        raise DownloadQuotaError(_remaining_hours(WINDOW_SECONDS))


def issue(
    db: Session,
    *,
    user_id: int,
    order_no: str,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """签发下载链接，返回 302 Location（/files/{token}）。

    校验链见模块 docstring；download_logs 与配额计数同事务提交。
    """
    o = get_user_order(db, user_id=user_id, order_no=order_no)  # 1. 本人+存在，否则 404
    if o.pay_status != "paid":
        # 2. 未支付/已取消/已撤销 → 403（统一 ORDER_NOT_PAID，不暴露具体态）
        raise BizError("订单未支付或已失效", status=403, code="ORDER_NOT_PAID")

    _check_and_count(db, o.id)  # 3. 配额检查+计数（Redis / DB 兜底 / 503）

    # 4. 消费前再查一次 pay_status（04 §5）：expire 后访问触发重查已提交值。
    #    真正的跨请求撤销窗口防护在 /files/{token} 端点消费时复核（见 files.py）。
    db.expire(o)
    if o.pay_status != "paid":
        raise BizError("订单未支付或已失效", status=403, code="ORDER_NOT_PAID")

    # 5. 留痕（Redis 丢数据时可据本表重建配额近似值）
    db.add(
        DownloadLog(
            order_id=o.id,
            ip=_sanitize_ip(ip),
            user_agent=(user_agent or "")[:500] or None,
            created_at=_utcnow(),
        )
    )
    db.commit()
    # 6. 签名短链 15min（core/signed_link：file|{order_id}）
    return signed_link.sign_file(o.id)
