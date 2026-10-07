"""审计日志查询与导出。仅管理员可查看和导出。"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.deps import get_current_user
from app.models import User
from app.services.audit_service import (
    OPERATION_LABELS,
    export_audit_logs,
    list_audit_logs,
    list_operators,
)

router = APIRouter()


def _require_admin(user: User) -> None:
    """审计日志的查看和导出都只对管理员开放。"""
    if user.role != "admin":
        raise ForbiddenError("需要管理员权限")


@router.get("/meta")
async def audit_meta(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """筛选项：操作类型和本租户用户。"""
    _require_admin(user)
    users = await list_operators(db, user.tenant_id)
    operations = [
        {"value": key, "label": label} for key, label in OPERATION_LABELS.items()
    ]
    return {"operations": operations, "users": users}


@router.get("/")
async def list_logs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID | None = Query(default=None),
    operation_type: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """按时间、用户、操作类型筛选最近一年的审计日志。"""
    _require_admin(user)
    items, total = await list_audit_logs(
        db,
        tenant_id=user.tenant_id,
        user_id=user_id,
        operation_type=operation_type or None,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/export")
async def export_logs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: UUID | None = Query(default=None),
    operation_type: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """按当前筛选导出 Excel。"""
    _require_admin(user)
    content = await export_audit_logs(
        db,
        tenant_id=user.tenant_id,
        user_id=user_id,
        operation_type=operation_type or None,
        start_date=start_date,
        end_date=end_date,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=audit-logs.xlsx",
        },
    )
