"""按会话加载窗口消息的查询语句。"""

from uuid import UUID

from sqlalchemy import select

from app.models import Message


def recent_messages_stmt(session_id: UUID, limit: int, exclude_id: UUID | None):
    """先排除本轮消息，再按时间倒序取 limit 条。"""
    stmt = select(Message).where(Message.session_id == session_id)
    if exclude_id is not None:
        stmt = stmt.where(Message.id != exclude_id)
    return stmt.order_by(Message.created_at.desc()).limit(limit)
