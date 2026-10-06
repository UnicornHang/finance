"""把本轮之前的消息收成模型可见的 20 条窗口，并按需召回更早片段。"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.budget import WINDOW_SIZE, HistoryItem, fit_window
from app.agent.memory.history_index import looks_like_history_reference, recall_history
from app.agent.memory.loader import recent_messages_stmt
from app.agent.memory.summary import fold_outside_window
from app.agent.router import Intent
from app.models import Message, Session
from app.services.chat_file_service import chat_file_service


@dataclass(frozen=True)
class AssembledContext:
    """history 的 content 已是 prompt 副本。related_history 无召回时为空。"""

    history: list[dict]
    window_ids: tuple[str, ...]
    window_count: int
    related_history: str = ""


async def _has_nonempty_outside(
    db: AsyncSession,
    session_id: UUID,
    exclude_message_id: UUID,
    window_ids: tuple[str, ...],
) -> bool:
    """窗口 id 与本轮消息之外是否还有非空正文。"""
    banned = [exclude_message_id, *[UUID(item_id) for item_id in window_ids]]
    stmt = (
        select(Message.id)
        .where(Message.session_id == session_id)
        .where(Message.id.notin_(banned))
        .where(Message.content.is_not(None))
        .where(func.length(func.trim(Message.content)) > 0)
        .limit(1)
    )
    found = await db.execute(stmt)
    return found.scalar_one_or_none() is not None


async def assemble_context(
    db: AsyncSession,
    session_id: UUID,
    exclude_message_id: UUID,
    session: Session | None = None,
    question: str = "",
    intent: str = "",
) -> AssembledContext:
    """加载本轮之前的最近 20 条，并生成 prompt 副本。

    session 为空时不折叠。折叠返回后，仅在意图不是 confirm_pending、窗口已满 20 条、
    窗口与本轮之外还有非空消息、且问题像在指代旧对话时召回。
    """
    result = await db.execute(
        recent_messages_stmt(session_id, WINDOW_SIZE, exclude_message_id)
    )
    messages = list(reversed(result.scalars().all()))
    files_by_message = await chat_file_service.list_by_message_ids(
        db, [m.id for m in messages]
    )
    items: list[HistoryItem] = []
    for message in messages:
        hint = chat_file_service.prompt_hint(files_by_message.get(message.id, []))
        content = (message.content or "").strip()
        if hint:
            content = f"{content}\n{hint}".strip() if content else hint
        if not content:
            continue
        created = getattr(message, "created_at", None)
        items.append(
            HistoryItem(
                id=str(message.id),
                role=message.role,
                content=content,
                created_at="" if created is None else str(created),
            )
        )
    fitted = fit_window(items)
    history = [
        {"role": item.role, "content": prompt}
        for item, prompt in zip(fitted.window, fitted.prompt_contents, strict=True)
    ]
    window_ids = tuple(item.id for item in fitted.window)
    window_count = len(fitted.window)
    # 三参数调用不传 session，保持只组装窗口、不写摘要
    if session is not None:
        await fold_outside_window(
            db,
            session,
            exclude_message_id=exclude_message_id,
            window_ids=window_ids,
        )
    related_history = ""
    # 折叠之后才召回。窗口未满、确认归档、或不是指代旧对话时不查向量
    if (
        session is not None
        and intent != Intent.CONFIRM_PENDING.value
        and window_count == WINDOW_SIZE
        and looks_like_history_reference(question)
        and await _has_nonempty_outside(
            db, session_id, exclude_message_id, window_ids
        )
    ):
        related_history = await recall_history(
            db,
            tenant_id=session.tenant_id,
            session_id=session_id,
            question=question,
            exclude_ids=set(window_ids) | {str(exclude_message_id)},
        )
    return AssembledContext(
        history=history,
        window_ids=window_ids,
        window_count=window_count,
        related_history=related_history,
    )
