"""会话服务。"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    from app.models import Session


class SessionService:
    """会话 CRUD + 访问控制。"""

    async def list_by_user(
        self, db: AsyncSession, user_id: UUID, tenant_id: UUID, limit: int = 100
    ) -> list["Session"]:
        """列出用户的活跃会话。"""
        from app.models import Session

        result = await db.execute(
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.tenant_id == tenant_id,
                Session.status == "active",
            )
            .order_by(Session.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, session_id: UUID) -> "Session | None":
        """根据 ID 查询会话。"""
        from app.models import Session

        return await db.get(Session, session_id)

    async def create(
        self, db: AsyncSession, user_id: UUID, tenant_id: UUID, title: str | None = None
    ) -> "Session":
        """创建会话。"""
        from app.models import Session

        session = Session(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            status="active",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def verify_access(
        self, db: AsyncSession, session_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> "Session":
        """校验会话归属，返回 Session；越权时抛 ForbiddenError。"""
        session = await self.get(db, session_id)
        if not session or session.status != "active":
            raise NotFoundError("会话不存在或已删除")
        if session.user_id != user_id or session.tenant_id != tenant_id:
            raise ForbiddenError("无权访问该会话")
        return session

    async def rename(
        self, db: AsyncSession, session_id: UUID, user_id: UUID, tenant_id: UUID, title: str
    ) -> "Session":
        """重命名会话。"""
        session = await self.verify_access(db, session_id, user_id, tenant_id)
        session.title = title
        await db.commit()
        await db.refresh(session)
        return session

    async def soft_delete(
        self, db: AsyncSession, session_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> None:
        """软删会话。"""
        session = await self.verify_access(db, session_id, user_id, tenant_id)
        session.status = "deleted"
        await db.commit()


session_service = SessionService()