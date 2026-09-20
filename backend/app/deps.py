"""FastAPI 依赖注入。"""

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.services.auth_service import auth_service

if TYPE_CHECKING:
    from app.models import User

# OAuth2 密码模式：FastAPI 自动从 Authorization: Bearer <token> 提取
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False,  # 自己处理 401 走统一异常处理
)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> "User":
    """从 JWT 解析当前用户。

    异常情况均抛 UnauthorizedError，走统一异常处理返回 401。
    """
    if not token:
        raise UnauthorizedError("未登录，请先登录")

    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise UnauthorizedError(f"无效的令牌：{exc}") from exc

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError("令牌缺少用户信息")

    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("无效的用户 ID") from exc

    user = await auth_service.get_by_id(db, user_id)
    if not user:
        raise UnauthorizedError("用户不存在")
    if user.status != "active":
        raise UnauthorizedError("账号已停用，请联系管理员")

    return user


def require_role(*roles: str):
    """角色守卫工厂：Depends(require_role("admin", "finance"))。"""

    async def _check(user: Annotated["User", Depends(get_current_user)]) -> "User":
        if user.role not in roles:
            from app.core.exceptions import ForbiddenError
            raise ForbiddenError("权限不足")
        return user

    return _check