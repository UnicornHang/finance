"""会话上下文对象 - 每次请求独立创建。"""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class SessionContext:
    """每个会话的独立上下文，无全局状态。

    包含四层上下文：
    - recent_messages: 最近 N 轮完整对话
    - summary: 中期摘要
    - entities: 结构化记忆
    - pending_task: 待确认任务
    """

    session_id: UUID
    user_id: UUID
    tenant_id: UUID

    recent_messages: list[dict] = field(default_factory=list)
    summary: str = ""
    entities: dict = field(default_factory=dict)
    pending_task: str | None = None

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
        from app.models import Session as SessionModel, Message, SessionMemory

        # 加载 session
        session = await db.get(SessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # 加载最近 20 条消息
        msg_stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        msg_result = await db.execute(msg_stmt)
        messages = list(reversed(msg_result.scalars().all()))

        # 加载结构化记忆
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
            pending_task=entities.get("pending_task"),
        )

    def build_prompt(self, user_input: str, rag_snippets: list[str] | None = None) -> list[dict]:
        """组装 LLM prompt。"""
        rag_text = "\n".join(rag_snippets or [])
        system = f"""你是企业财务 AI 助手。

[会话摘要]
{self.summary}

[当前状态]
待确认任务：{self.pending_task}
已上传单据：{self.entities.get('uploaded_invoices', [])}

[相关历史]
{rag_text}
"""
        return [
            {"role": "system", "content": system},
            *self.recent_messages[-20:],
            {"role": "user", "content": user_input},
        ]