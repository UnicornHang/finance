"""LLM token 用量解析与落库。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LlmUsageEvent, Session

logger = logging.getLogger(__name__)


def _as_uuid(value: UUID | str | None) -> UUID | None:
    """将 UUID / 字符串规范化为 UUID；None 原样返回。"""
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def parse_usage(raw: Any) -> tuple[int, int, int, bool]:
    """从 dict / 对象 / None 解析 (prompt, completion, total, usage_missing)。"""
    if raw is None:
        return 0, 0, 0, True

    def _get(key: str) -> int | None:
        if isinstance(raw, dict):
            v = raw.get(key)
        else:
            v = getattr(raw, key, None)
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    prompt = _get("prompt_tokens")
    completion = _get("completion_tokens")
    total = _get("total_tokens")
    if prompt is None and completion is None and total is None:
        return 0, 0, 0, True
    p = prompt or 0
    c = completion or 0
    t = total if total is not None else p + c
    # 仅有 total、无 prompt/completion 时也视为 missing 的分项
    missing = prompt is None and completion is None
    return p, c, t, missing


async def record_llm_usage(
    *,
    db: AsyncSession | None,
    tenant_id: UUID | str | None,
    scene: str = "unknown",
    source: str = "complete",
    session_id: UUID | str | None = None,
    user_id: UUID | str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    usage_missing: bool = False,
) -> None:
    """写入用量事件；有 session 则累加。失败只记日志。"""
    if db is None or tenant_id is None:
        logger.warning("llm usage 跳过：缺少 db 或 tenant_id scene=%s", scene)
        return
    try:
        # UUID 解析与写库均在 try 内，避免无效 id 冒泡打断调用方
        tid = _as_uuid(tenant_id)
        if tid is None:
            logger.warning("llm usage 跳过：缺少 db 或 tenant_id scene=%s", scene)
            return
        sid = _as_uuid(session_id)
        uid = _as_uuid(user_id)
        event = LlmUsageEvent(
            id=uuid4(),
            tenant_id=tid,
            session_id=sid,
            user_id=uid,
            scene=scene or "unknown",
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            usage_missing=usage_missing,
            source=source,
        )
        # savepoint：INSERT/UPDATE 失败只回滚嵌套事务，外层聊天会话可继续
        async with db.begin_nested():
            db.add(event)
            if sid is not None:
                await db.execute(
                    update(Session)
                    .where(Session.id == sid, Session.tenant_id == tid)
                    .values(
                        prompt_tokens_total=Session.prompt_tokens_total + prompt_tokens,
                        completion_tokens_total=Session.completion_tokens_total + completion_tokens,
                        total_tokens=Session.total_tokens + total_tokens,
                    )
                )
            await db.flush()
    except Exception:
        logger.exception("llm usage 落库失败 scene=%s", scene)
