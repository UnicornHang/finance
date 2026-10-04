"""会话上下文对象 - 每次请求独立创建。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.agent.memory.entities import (
    LAST_INTENT,
    PENDING_TASK,
    QUERIED_POLICIES,
    UPLOADED_CONTRACTS,
    UPLOADED_INVOICES,
)
from app.agent.router import Intent

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """每个会话的独立上下文，无全局状态。

    包含四层上下文：
    - recent_messages: 最近 N 轮完整对话
    - summary: 中期摘要
    - entities: 结构化记忆
    - pending_task: 待确认任务种类
    """

    session_id: UUID
    user_id: UUID
    tenant_id: UUID

    recent_messages: list[dict] = field(default_factory=list)
    summary: str = ""
    entities: dict = field(default_factory=dict)
    pending_task: str | None = None

    @classmethod
    def empty(
        cls,
        session_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        *,
        summary: str = "",
    ) -> "SessionContext":
        """测试或加载失败时的空上下文。"""
        return cls(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            summary=summary or "",
        )

    @classmethod
    async def load(
        cls,
        session_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        db,
    ) -> "SessionContext":
        """从 DB 加载当前 session 的上下文。"""
        from sqlalchemy import select

        from app.models import Message
        from app.models import Session as SessionModel
        from app.models import SessionMemory

        session = await db.get(SessionModel, session_id)
        if not isinstance(session, SessionModel):
            raise ValueError(f"Session {session_id} not found")

        msg_stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        msg_result = await db.execute(msg_stmt)
        messages = list(reversed(msg_result.scalars().all()))

        mem_stmt = select(SessionMemory).where(SessionMemory.session_id == session_id)
        mem_result = await db.execute(mem_stmt)
        mems = mem_result.scalars().all()
        entities = {m.entity_type: m.entity_value for m in mems}

        return cls(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            recent_messages=[
                {"role": m.role, "content": m.content} for m in messages
            ],
            summary=session.summary or "",
            entities=entities,
            pending_task=_pending_kind(entities.get(PENDING_TASK)),
        )

    @classmethod
    async def load_safe(
        cls,
        session_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        db,
        *,
        fallback_summary: str = "",
    ) -> "SessionContext":
        """加载失败时返回空上下文，不打断对话。"""
        try:
            return await cls.load(session_id, user_id, tenant_id, db)
        except Exception:
            logger.exception("SessionContext.load failed session=%s", session_id)
            return cls.empty(
                session_id, user_id, tenant_id, summary=fallback_summary
            )

    def last_intent(self) -> Intent | None:
        """上一轮最终采用的意图。"""
        raw = self.entities.get(LAST_INTENT)
        value = None
        if isinstance(raw, dict):
            value = raw.get("value")
        elif isinstance(raw, str):
            value = raw
        if not value:
            return None
        try:
            return Intent(value)
        except ValueError:
            return None

    def memory_block(self) -> str:
        """注入 system 的摘要与待办块。"""
        pending = self.entities.get(PENDING_TASK)
        kind = _pending_kind(pending) or "none"
        pending_id = ""
        if isinstance(pending, dict):
            pending_id = str(pending.get("id") or "")
        invoice_ids = _entity_ids(self.entities.get(UPLOADED_INVOICES))
        contract_ids = _entity_ids(self.entities.get(UPLOADED_CONTRACTS))
        titles = []
        policies = self.entities.get(QUERIED_POLICIES)
        if isinstance(policies, dict):
            raw = policies.get("titles") or []
            if isinstance(raw, list):
                titles = [str(x) for x in raw][-5:]
        return (
            "[会话摘要]\n"
            f"{(self.summary or '').strip() or '（无）'}\n\n"
            "[当前状态]\n"
            f"pending_task: {kind}\n"
            f"pending_ids: {pending_id or '（无）'}\n"
            f"uploaded_invoices: {', '.join(invoice_ids) or '（无）'}\n"
            f"uploaded_contracts: {', '.join(contract_ids) or '（无）'}\n"
            f"queried_policies: {', '.join(titles) or '（无）'}"
        )

    def build_prompt(self, user_input: str, rag_snippets: list[str] | None = None) -> list[dict]:
        """组装 LLM prompt。"""
        rag_text = "\n".join(rag_snippets or [])
        system = f"""你是企业财务 AI 助手。

{self.memory_block()}

[相关历史]
{rag_text}
"""
        return [
            {"role": "system", "content": system},
            *self.recent_messages[-20:],
            {"role": "user", "content": user_input},
        ]


def attach_memory(system_prompt: str, ctx: SessionContext | None) -> str:
    """人设在前，记忆块在后。"""
    if ctx is None:
        return system_prompt
    return f"{system_prompt}\n\n{ctx.memory_block()}"


def _pending_kind(raw: object) -> str | None:
    """pending_task JSON 或旧字符串。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        kind = raw.get("kind")
        if kind and kind != "none":
            return str(kind)
        return None
    text = str(raw).strip()
    return text or None


def _entity_ids(raw: object) -> list[str]:
    """取出 ids 列表。"""
    if isinstance(raw, dict):
        ids = raw.get("ids") or []
        if isinstance(ids, list):
            return [str(x) for x in ids][-8:]
    if isinstance(raw, list):
        return [str(x) for x in raw][-8:]
    return []
