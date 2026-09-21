"""审计日志服务 - 统一写入 AuditLog。

用法：
    await write_audit_log(db, tenant_id=..., user_id=..., operation_type=..., ...)
    # 不 commit，跟调用方同事务
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def write_audit_log(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    operation_type: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    ua: str | None = None,
    result: str = "success",
    error_message: str | None = None,
) -> None:
    """写入一条审计日志。`flush` 而非 `commit`，让调用方控制事务边界。"""
    from app.models import AuditLog

    log = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
        before_value=before,
        after_value=after,
        ip=ip,
        ua=ua,
        result=result,
        error_message=error_message,
    )
    db.add(log)
    try:
        await db.flush()
    except Exception as exc:
        logger.warning("audit log flush failed: %s (operation=%s target=%s)", exc, operation_type, target_id)