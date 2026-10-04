"""摘要更新 - 滚动压缩历史对话。"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Session as SessionModel
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SUMMARY_EVERY = 10


async def update_summary(session_id: str, old_summary: str, recent_messages: list[dict]) -> str:
    """更新会话摘要。"""
    msgs_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages[-20:])
    prompt = f"""旧摘要：{old_summary}

最近对话：
{msgs_text}

请更新摘要，保留关键信息：上传的单据、查询的制度、待办任务、用户偏好。
控制在 200 字以内。
"""
    return await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="chitchat",
        apply_scene_prompt=False,
    )


async def maybe_roll_summary(
    db: AsyncSession,
    session: SessionModel,
    recent_messages: list[dict],
) -> None:
    """消息条数达到 10 的倍数时滚动摘要；失败不影响主对话。"""
    try:
        total = await db.scalar(
            select(func.count()).select_from(Message).where(Message.session_id == session.id)
        )
        if not total or int(total) % SUMMARY_EVERY != 0:
            return
        text = await update_summary(str(session.id), session.summary or "", recent_messages)
        trimmed = (text or "").strip()[:200]
        if trimmed:
            session.summary = trimmed
            await db.commit()
    except Exception:
        logger.exception("maybe_roll_summary failed session=%s", getattr(session, "id", None))
