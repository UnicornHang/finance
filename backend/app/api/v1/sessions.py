"""会话管理 API。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models import Message, User
from app.services.chat_file_service import chat_file_service
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


def _message_attachments(message: Message, rows: list) -> list[dict] | None:
    """优先用 chat_files。没有行时再读消息上残留的 JSON。"""
    if rows:
        return [chat_file_service.to_attachment(row) for row in rows]
    stored = message.attachments
    if isinstance(stored, list) and stored:
        return [item for item in stored if isinstance(item, dict)]
    tool_calls = message.tool_calls
    if not isinstance(tool_calls, dict):
        return None
    nested = tool_calls.get("attachments")
    if not isinstance(nested, list) or not nested:
        return None
    return [item for item in nested if isinstance(item, dict)]


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """会话消息列表（按时间正序）。"""
    # 先校验会话归属
    await session_service.verify_access(db, session_id, user.id, user.tenant_id)

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(500)
    )
    messages = result.scalars().all()
    files_by_message = await chat_file_service.list_by_message_ids(db, [m.id for m in messages])

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "attachments": _message_attachments(m, files_by_message.get(m.id, [])),
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]