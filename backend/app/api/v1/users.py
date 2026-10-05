"""用户管理 API（仅管理员）。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.deps import get_current_user
from app.models import User
from app.schemas import PasswordResetOut, UserCreate, UserOut, UserUpdate
from app.services.user_service import user_service

router = APIRouter()


def _require_admin(user: User) -> None:
    """用户管理仅管理员可操作，财务无权改账号。"""
    if user.role != "admin":
        raise ForbiddenError("需要管理员权限")


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    """提取审计用 IP 与 UA。"""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


@router.get("/", response_model=list[UserOut])
async def list_users(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """当前租户用户列表。"""
    _require_admin(user)
    return await user_service.list_users(db, user.tenant_id)


@router.post("/", response_model=UserOut)
async def create_user(
    payload: UserCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """创建用户并分配角色。"""
    _require_admin(user)
    ip, ua = _client_meta(request)
    return await user_service.create_user(db, actor=user, payload=payload, ip=ip, ua=ua)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新用户（角色/部门/状态）。"""
    _require_admin(user)
    ip, ua = _client_meta(request)
    return await user_service.update_user(
        db, actor=user, user_id=user_id, payload=payload, ip=ip, ua=ua
    )


@router.post("/{user_id}/reset-password", response_model=PasswordResetOut)
async def reset_password(
    user_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """重置密码，响应中仅出现一次临时密码。"""
    _require_admin(user)
    ip, ua = _client_meta(request)
    return await user_service.reset_password(
        db, actor=user, user_id=user_id, ip=ip, ua=ua
    )


@router.delete("/{user_id}", response_model=UserOut)
async def delete_user(
    user_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """停用用户（软删除，保留历史单据外键）。"""
    _require_admin(user)
    ip, ua = _client_meta(request)
    return await user_service.disable_user(
        db, actor=user, user_id=user_id, ip=ip, ua=ua
    )
