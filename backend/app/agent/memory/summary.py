"""窗口外摘要折叠。"""

import logging
from uuid import UUID

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm.attributes import set_committed_value

from app.models import Message, Session as SessionModel
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SUMMARY_CHAR_CAP = 800
SUMMARY_BATCH_CHARS = 8000


def build_summary_prompt(old_summary: str, lines: list[str]) -> str:
    """窗口外消息的折叠提示。"""
    body = "\n".join(lines)
    return f"""旧摘要：{old_summary or "（无）"}

需要折入摘要的更早对话：
{body}

请更新摘要。保留金额、税额、销方、制度结论、用户纠正过的事实、未完成的问题。
单据 id 以会话结构化记忆为准，不要复制 id 清单。
控制在 800 字以内。
"""


def split_fold_batches(lines: list[str], max_chars: int = 8000) -> list[list[str]]:
    """按行累加字符数分批。当前批加上该行会超限且当前批非空时开新批；单行超限则单独成批。"""
    batches: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line)
        # 当前批放不下这一行时先封批，避免把超限行和上一批粘在一起
        if current and current_len + line_len > max_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
        if line_len > max_chars:
            batches.append(current)
            current = []
            current_len = 0
    if current:
        batches.append(current)
    return batches


async def update_summary(
    session_id: str,
    old_summary: str,
    lines: list[str],
    *,
    db: AsyncSession | None = None,
    tenant_id: str | UUID | None = None,
    user_id: str | UUID | None = None,
) -> str:
    """用传入的 lines 更新摘要，截到 800 字。不再截最近 20 条。"""
    prompt = build_summary_prompt(old_summary, lines)
    text = await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="chitchat",
        apply_scene_prompt=False,
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
    )
    trimmed = (text or "").strip()[:SUMMARY_CHAR_CAP]
    logger.info("update_summary session=%s chars=%s", session_id, len(trimmed))
    return trimmed


async def _outside_lines(
    db: AsyncSession,
    session: SessionModel,
    exclude_message_id: UUID,
    window_ids: tuple[str, ...],
) -> tuple[list[str], UUID | None]:
    """查询窗口外、游标之后、正文非空的消息。没有待折叠行时返回 ([], None)。"""
    excluded = {UUID(str(item)) for item in window_ids}
    excluded.add(exclude_message_id)
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session.id)
        .where(Message.id.notin_(excluded))
        .where(Message.content.is_not(None))
        .where(func.length(func.trim(Message.content)) > 0)
        .order_by(Message.created_at.asc())
    )
    rows = list(result.scalars().all())
    cursor_id = session.summary_until_message_id
    if cursor_id is not None:
        cursor_result = await db.execute(
            select(Message.created_at).where(Message.id == cursor_id)
        )
        cursor_at = cursor_result.scalar_one_or_none()
        # 游标指向的消息已不存在时当作游标为空，折叠全部窗口外消息
        if cursor_at is not None:
            rows = [row for row in rows if row.created_at > cursor_at]
    lines: list[str] = []
    last_id: UUID | None = None
    for row in rows:
        text = (row.content or "").strip()
        if not text:
            continue
        lines.append(f"{row.role}: {text}")
        last_id = row.id
    if not lines or last_id is None:
        return [], None
    return lines, last_id


def _loaded_snapshot(db: AsyncSession) -> list[tuple[object, dict]]:
    """记下本请求已加载对象。rollback 会把它们过期，失败路径需要写回内存。"""
    sync = getattr(db, "sync_session", None)
    if not isinstance(sync, OrmSession):
        return []
    snaps: list[tuple[object, dict]] = []
    for obj in list(sync.identity_map.values()):
        snaps.append((obj, dict(inspect(obj).dict)))
    return snaps


def _restore_loaded(snaps: list[tuple[object, dict]]) -> None:
    """把 rollback 前已加载的属性写回，避免本轮再懒加载。单个字段失败不影响其余字段。"""
    for obj, data in snaps:
        for key, value in data.items():
            try:
                set_committed_value(obj, key, value)
            except Exception:
                logger.exception("restore loaded attribute failed key=%s", key)


async def _rollback_keep_loaded(db: AsyncSession, snaps: list[tuple[object, dict]]) -> None:
    """回滚未提交的摘要写入，并恢复本请求里已经加载的对象。"""
    await db.rollback()
    try:
        _restore_loaded(snaps)
    except Exception:
        logger.exception("restore after summary rollback failed")


async def fold_outside_window(
    db: AsyncSession,
    session: SessionModel,
    *,
    exclude_message_id: UUID,
    window_ids: tuple[str, ...],
) -> None:
    """窗口满 20 条时，把窗口外未覆盖的消息折进摘要。失败不改摘要和游标。"""
    # 窗口未满时不查库、不调用摘要模型
    if len(window_ids) < 20:
        return
    snaps: list[tuple[object, dict]] = []
    try:
        snaps = _loaded_snapshot(db)
        lines, last_id = await _outside_lines(
            db, session, exclude_message_id, window_ids
        )
        if not lines or last_id is None:
            return
        folded = session.summary or ""
        for batch in split_fold_batches(lines, SUMMARY_BATCH_CHARS):
            folded = await update_summary(
                str(session.id),
                folded,
                batch,
                db=db,
                tenant_id=str(session.tenant_id),
                user_id=str(session.user_id),
            )
            if not folded:
                break
        if not folded:
            logger.exception(
                "fold_outside_window empty summary session=%s",
                getattr(session, "id", None),
            )
            await _rollback_keep_loaded(db, snaps)
            return
        session.summary = folded[:SUMMARY_CHAR_CAP]
        session.summary_until_message_id = last_id
        await db.commit()
    except Exception:
        logger.exception(
            "fold_outside_window failed session=%s",
            getattr(session, "id", None),
        )
        await _rollback_keep_loaded(db, snaps)
