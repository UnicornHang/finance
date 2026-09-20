"""认证 API：登录、刷新、登出。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.deps import get_current_user
from app.models import User
from app.services.auth_service import auth_service

router = APIRouter()


def _build_user_dict(user) -> dict:
    """构造前端需要的 user 字段。"""
    return {
        "id": str(user.id),
        "name": user.name,
        "account": user.account,
        "role": user.role,
        "dept": user.dept,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _build_token_response(user, access_token: str, refresh_token: str) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": _build_user_dict(user),
    }


@router.post("/login")
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """账号密码登录，返回 Access Token + Refresh Token + 用户信息。

    OAuth2 标准：username + password 表单字段。
    """
    user = await auth_service.authenticate(db, form.username, form.password)

    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    return _build_token_response(user, access_token, refresh_token)


@router.post("/refresh")
async def refresh(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
):
    """用 Refresh Token 换新的 Access Token。"""
    try:
        payload = decode_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的刷新令牌：{exc}",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌类型错误",
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌",
        )

    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的用户 ID",
        )

    user = await auth_service.get_by_id(db, user_id)
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已停用",
        )

    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
    )
    new_refresh_token = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    return _build_token_response(user, access_token, new_refresh_token)


@router.post("/logout")
async def logout():
    """登出。

    JWT 是无状态的，真正的登出靠客户端清除 Token。
    服务端可选：维护 Token 黑名单（Redis）。
    MVP 阶段：直接返回成功。
    """
    return {"message": "logged out"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息（用于刷新用户态）。"""
    return _build_user_dict(user)