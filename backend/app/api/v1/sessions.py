"""会话管理 API。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services.session_service import session_service

router = APIRouter()


# ================ Schemas ================

class SessionCreate(BaseModel):
    title: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None


def _serialize(session) -> dict:
    return {
        "id": str(session.id),
        "title": session.title,
        "summary": session.summary,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


# ================ Endpoints ================

@router.get("/")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的活跃会话列表（按更新时间倒序）。"""
    sessions = await session_service.list_by_user(
        db, user.id, user.tenant_id, limit=100
    )
    return [_serialize(s) for s in sessions]


@router.post("/")
async def create_session(
    body: SessionCreate | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新建会话。"""
    title = body.title if body else None
    session = await session_service.create(
        db, user.id, user.tenant_id, title=title
    )
    return _serialize(session)


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话详情。"""
    session = await session_service.verify_access(
        db, session_id, user.id, user.tenant_id
    )
    return _serialize(session)


@router.patch("/{session_id}")
async def update_session(
    session_id: UUID,
    body: SessionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名会话。"""
    if body.title is None:
        return {"message": "nothing to update"}
    session = await session_service.rename(
        db, session_id, user.id, user.tenant_id, body.title
    )
    return _serialize(session)


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """软删会话。"""
    await session_service.soft_delete(
        db, session_id, user.id, user.tenant_id
    )
    return {"message": "deleted", "session_id": str(session_id)}


def _extract_attachments(tool_calls: dict | None) -> list[dict] | None:
    """从 tool_calls.attachments 提取附件列表（用户上传文件回显用）。"""
    if not isinstance(tool_calls, dict):
        return None
    atts = tool_calls.get("attachments")
    if not isinstance(atts, list) or not atts:
        return None
    return [a for a in atts if isinstance(a, dict)]


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话消息列表（按时间正序）。"""
    from sqlalchemy import select
    from app.models import Message

    # 先校验会话归属
    await session_service.verify_access(db, session_id, user.id, user.tenant_id)

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(500)
    )
    messages = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "attachments": _extract_attachments(m.tool_calls),
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]