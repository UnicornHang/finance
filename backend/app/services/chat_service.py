"""Chat 编排服务。

负责消息持久化、上下文组装、LLM 流式输出。
Phase A：支持文件上传触发 OCR 异步任务，OCR 完成后写 Invoice 供前端轮询。
"""

import logging
from typing import TYPE_CHECKING, AsyncGenerator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import llm_service
from app.services.session_service import session_service

if TYPE_CHECKING:
    from app.models import Message, Session, User

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是企业财务 AI 助手，名叫「¥ 小财」。

你可以帮助用户：
1. 识别并归档发票（用户上传发票图片/PDF 后，你调用 ocr_invoice 工具）
2. 审查合同合规性（用户上传合同后，你调用 review_contract 工具）
3. 回答企业制度问题（使用 RAG 检索）

回答要求：
- 用简洁、专业的中文
- 不确定的内容明确告知用户
- 涉及金额、日期、合同条款等关键信息要准确
- 必要时引导用户提供更具体的上下文
"""


class ChatService:
    """Chat 消息持久化 + 流式响应编排。"""

    async def save_message(
        self,
        db: AsyncSession,
        session_id: UUID,
        tenant_id: UUID,
        role: str,
        content: str,
        tool_calls: dict | None = None,
    ) -> "Message":
        """持久化单条消息。"""
        from app.models import Message

        msg = Message(
            tenant_id=tenant_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg

    async def load_recent_messages(
        self, db: AsyncSession, session_id: UUID, limit: int = 20
    ) -> list[dict]:
        """加载最近 N 轮对话（按时间正序）。"""
        from app.models import Message

        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(reversed(result.scalars().all()))
        return [
            {"role": m.role, "content": m.content or ""}
            for m in messages
            if m.content
        ]

    async def auto_title(self, db: AsyncSession, session: "Session", first_message: str) -> None:
        """根据首条用户消息自动生成会话标题。"""
        if session.title:
            return
        title = first_message.strip()
        if len(title) > 30:
            title = title[:30] + "…"
        session.title = title
        await db.commit()

    async def stream_response(
        self,
        db: AsyncSession,
        user: "User",
        session_id: UUID,
        user_message: str,
        *,
        file_url: str | None = None,
        file_hash: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """流式处理用户输入，yield SSE 事件字典。

        事件类型：
        - {type: "session", session_id: "..."}  ：会话确认（新建会话时）
        - {type: "text", content: "..."}        ：增量文本
        - {type: "sidepanel", payload: {...}}   ：侧弹窗（OCR 上传时触发）
        - {type: "done"}                       ：流结束
        - {type: "error", message: "..."}       ：错误

        文件上传分支（Phase A）：
        1. 持久化用户消息（含文件名）
        2. 触发 Celery process_invoice_ocr.delay(...)
        3. 立即 yield sidepanel{status:'processing'} + text + done
        4. 前端轮询 GET /invoices/preview/by-hash/{hash} 获取 OCR 结果
        """
        # 1. 校验会话归属
        try:
            session = await session_service.verify_access(
                db, session_id, user.id, user.tenant_id
            )
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            return

        # 2. 持久化用户消息
        await self.save_message(
            db, session_id, user.tenant_id, "user", user_message
        )

        # ========== Phase A：文件上传分支 ==========
        if file_url and file_hash:
            try:
                # 触发 Celery（异步，不 await）
                from app.tasks.ocr_task import process_invoice_ocr

                process_invoice_ocr.delay(
                    tenant_id=str(user.tenant_id),
                    user_id=str(user.id),
                    file_url=file_url,
                    file_hash=file_hash,
                    user_message=user_message or None,
                )
                logger.info(
                    "OCR task dispatched: tenant=%s hash=%s session=%s",
                    user.tenant_id, file_hash, session_id,
                )

                # 推 sidepanel processing 事件
                yield {
                    "type": "sidepanel",
                    "payload": {
                        "type": "invoice",
                        "data": {
                            "status": "processing",
                            "file_url": file_url,
                            "file_hash": file_hash,
                        },
                    },
                }
                yield {"type": "text", "content": "正在识别发票字段，请稍候…"}
                yield {"type": "done"}
                return
            except Exception as exc:
                logger.exception("Failed to dispatch OCR task")
                yield {"type": "error", "message": f"OCR 任务派发失败：{exc}"}
                return

        # ========== 常规对话分支（保持原逻辑） ==========
        # 3. 加载上下文
        history = await self.load_recent_messages(db, session_id, limit=20)
        # 移除刚保存的用户消息（避免重复）
        history = [m for m in history if not (m["role"] == "user" and m["content"] == user_message)]
        # history[-1] 仍是用户消息（DB 写入时间 < 读取时间）
        if history and history[-1]["content"] == user_message:
            history = history[:-1]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history[-20:],
            {"role": "user", "content": user_message},
        ]

        # 4. 流式调用 LLM
        assistant_content = ""
        try:
            async for chunk in llm_service.stream(
                messages,
                scene="chitchat",
                db=db,
                tenant_id=str(user.tenant_id),
            ):
                assistant_content += chunk
                yield {"type": "text", "content": chunk}
        except Exception as exc:
            logger.exception("LLM 调用失败")
            yield {"type": "error", "message": f"AI 调用失败：{exc}"}
            # 即使失败也保存已收到的部分
            if assistant_content:
                await self.save_message(
                    db, session_id, user.tenant_id, "assistant", assistant_content
                )
            return

        # 5. 持久化助手消息
        if assistant_content.strip():
            await self.save_message(
                db, session_id, user.tenant_id, "assistant", assistant_content
            )
            # 首条消息时自动生成标题
            if not history or len(history) <= 1:
                await self.auto_title(db, session, user_message)

        # 6. 流结束
        yield {"type": "done"}


chat_service = ChatService()