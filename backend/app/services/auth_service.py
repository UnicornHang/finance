"""用户认证服务。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import verify_password
from app.models import User


class AuthService:
    """用户认证 + 查询。"""

    async def authenticate(self, db: AsyncSession, account: str, password: str) -> User:
        """验证账号密码，返回用户对象。

        故意对「用户不存在」和「密码错误」返回相同错误，避免账号枚举攻击。
        """
        result = await db.execute(select(User).where(User.account == account))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash or ""):
            raise UnauthorizedError("账号或密码错误")

        if user.status != "active":
            raise UnauthorizedError("账号已停用，请联系管理员")

        return user

    async def get_by_id(self, db: AsyncSession, user_id: UUID) -> User | None:
        """根据 ID 查询用户。"""
        return await db.get(User, user_id)


auth_service = AuthService()