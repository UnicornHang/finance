"""数据概览 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.deps import get_current_user
from app.models import User
from app.services.dashboard_service import dashboard_service

router = APIRouter()

_ALLOWED_ROLES = frozenset({"admin", "finance"})


def _require_dashboard(user: User) -> None:
    """数据概览仅财务与管理员可看。"""
    if user.role not in _ALLOWED_ROLES:
        raise ForbiddenError("需要财务或管理员权限")


@router.get("/overview")
async def get_overview(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=7, le=30)] = 7,
):
    """首页看板：KPI、归档趋势、风险合同、最近归档。"""
    _require_dashboard(user)
    return await dashboard_service.overview(db, tenant_id=user.tenant_id, days=days)
