"""审计日志（06 §7 / 03 audit_logs）。只增不改不删。"""
import ipaddress

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def _valid_ip(ip: str | None) -> str | None:
    """audit_logs.ip 为 INET 列；非法值（如测试客户端 'testclient'）→ None，避免整事务 500。"""
    if ip is None:
        return None
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


def record(
    db: Session,
    *,
    admin_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    reason: str | None = None,
    ip: str | None = None,
) -> None:
    """写一条审计（不 commit，由调用方事务统一提交）。"""
    db.add(
        AuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            ip=_valid_ip(ip),
        )
    )
