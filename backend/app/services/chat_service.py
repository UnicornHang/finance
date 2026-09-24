"""Chat 编排服务。

负责消息持久化、上下文组装、LLM 流式输出。
方案 B 验证：上传发票时 Vision 主识别 → OCR 兜底 → 入库侧栏 → 模型带着结果回复。
"""

import logging
from typing import TYPE_CHECKING, AsyncGenerator, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.services.llm_service import llm_service
from app.services.session_service import session_service

if TYPE_CHECKING:
    from app.models import Message, Session, User

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是企业财务 AI 助手，名叫「¥ 小财」。

你可以帮助用户：
1. 识别并归档发票（用户上传发票图片/PDF）
2. 审查合同合规性
3. 回答企业制度问题（使用 RAG 检索）

回答要求：
- 用简洁、专业的中文
- 不确定的内容明确告知用户
- 涉及金额、日期、合同条款等关键信息要准确
- 必要时引导用户提供更具体的上下文
"""


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    """s3://bucket/key → (bucket, key)"""
    if not s3_url.startswith("s3://"):
        raise ValueError(f"invalid s3 url: {s3_url}")
    rest = s3_url[len("s3://") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid s3 url: {s3_url}")
    return bucket, key


def _download_bytes(file_url: str) -> bytes:
    """从 MinIO 下载对象为 bytes。"""
    from app.services.storage_service import storage_service

    bucket, key = _parse_s3_url(file_url)
    obj = storage_service.client.get_object(bucket_name=bucket, object_name=key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()


def _result_to_fields(result) -> dict[str, Any]:
    """InvoiceOCRResult → create_pending kwargs。"""
    return {
        "invoice_title": result.invoice_title,
        "company": result.company,
        "tax_id": result.tax_id,
        "invoice_code": result.invoice_code,
        "invoice_number": result.invoice_number,
        "invoice_date": result.invoice_date,
        "amount_excl_tax": result.amount_excl_tax,
        "tax_amount": result.tax_amount,
        "amount_incl_tax": result.amount_incl_tax,
        "invoice_type": result.invoice_type,
        "seller": result.seller,
        "buyer": result.buyer,
        "confidence": result.confidence,
    }


def _serialize_invoice(inv) -> dict[str, Any]:
    """侧栏 / SSE 用的发票字典。"""
    return {
        "id": str(inv.id),
        "invoice_title": inv.invoice_title,
        "company": inv.company,
        "tax_id": inv.tax_id,
        "invoice_code": inv.invoice_code,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "amount_excl_tax": float(inv.amount_excl_tax) if inv.amount_excl_tax is not None else None,
        "tax_amount": float(inv.tax_amount) if inv.tax_amount is not None else None,
        "amount_incl_tax": float(inv.amount_incl_tax) if inv.amount_incl_tax is not None else None,
        "invoice_type": inv.invoice_type,
        "seller": inv.seller,
        "buyer": inv.buyer,
        "remark": inv.remark,
        "file_url": inv.file_url,
        "file_hash": inv.file_hash,
        "ocr_confidence": inv.ocr_confidence,
        "status": inv.status,
    }


def _format_result_for_prompt(fields: dict[str, Any], source: str) -> str:
    """把结构化结果写成模型可读摘要。"""
    lines = [
        f"识别来源：{'多模态模型(Vision)' if source == 'vision' else 'OCR 引擎'}",
        f"发票号码：{fields.get('invoice_number') or '—'}",
        f"发票代码：{fields.get('invoice_code') or '—'}",
        f"开票日期：{fields.get('invoice_date') or '—'}",
        f"销售方：{fields.get('seller') or fields.get('company') or '—'}",
        f"购买方：{fields.get('buyer') or '—'}",
        f"税号：{fields.get('tax_id') or '—'}",
        f"金额(不含税)：{fields.get('amount_excl_tax') if fields.get('amount_excl_tax') is not None else '—'}",
        f"税额：{fields.get('tax_amount') if fields.get('tax_amount') is not None else '—'}",
        f"价税合计：{fields.get('amount_incl_tax') if fields.get('amount_incl_tax') is not None else '—'}",
        f"发票类型：{fields.get('invoice_type') or '—'}",
    ]
    return "\n".join(lines)


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
        file_meta: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """流式处理用户输入，yield SSE 事件字典。

        文件上传（方案 B 验证）：
        1. 推 sidepanel processing
        2. Vision 识别 → 失败则 OCR
        3. 写 pending_review，推 sidepanel ready
        4. 带着结构化结果流式回复用户
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
        display_msg = user_message or "（上传了发票文件）"
        await self.save_message(
            db, session_id, user.tenant_id, "user", display_msg
        )

        # ========== 方案 B：发票文件分支 ==========
        if file_url and file_hash:
            async for event in self._stream_invoice_recognize(
                db,
                user,
                session,
                session_id,
                user_message=user_message,
                file_url=file_url,
                file_hash=file_hash,
                file_meta=file_meta or {},
            ):
                yield event
            return

        # ========== 常规对话分支 ==========
        history = await self.load_recent_messages(db, session_id, limit=20)
        history = [m for m in history if not (m["role"] == "user" and m["content"] == display_msg)]
        if history and history[-1]["content"] == display_msg:
            history = history[:-1]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history[-20:],
            {"role": "user", "content": display_msg},
        ]

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
            if assistant_content:
                await self.save_message(
                    db, session_id, user.tenant_id, "assistant", assistant_content
                )
            return

        if assistant_content.strip():
            await self.save_message(
                db, session_id, user.tenant_id, "assistant", assistant_content
            )
            if not history or len(history) <= 1:
                await self.auto_title(db, session, display_msg)

        yield {"type": "done"}

    async def _stream_invoice_recognize(
        self,
        db: AsyncSession,
        user: "User",
        session: "Session",
        session_id: UUID,
        *,
        user_message: str,
        file_url: str,
        file_hash: str,
        file_meta: dict,
    ) -> AsyncGenerator[dict, None]:
        """Vision 主路径 + OCR 兜底 + 侧栏 + 带结果回复。"""
        from app.services.invoice_service import invoice_service
        from app.services.invoice_vision_service import invoice_vision_service

        # 先告诉前端进入识别中（轮询仍可用）
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
        yield {"type": "text", "content": "正在识别发票（优先多模态模型，失败将回落 OCR）…\n\n"}

        try:
            file_bytes = _download_bytes(file_url)
        except Exception as exc:
            logger.exception("download invoice failed")
            yield {"type": "error", "message": f"下载发票文件失败：{exc}"}
            yield {"type": "done"}
            return

        content_type = file_meta.get("content_type")
        filename = file_meta.get("original_filename")

        try:
            result, source = await invoice_vision_service.recognize(
                file_bytes,
                content_type=content_type,
                filename=filename,
                db=db,
                tenant_id=str(user.tenant_id),
            )
        except Exception as exc:
            logger.exception("invoice recognize failed")
            yield {"type": "error", "message": f"发票识别失败：{exc}"}
            yield {"type": "done"}
            return

        fields = _result_to_fields(result)

        try:
            inv = await invoice_service.create_pending(
                db,
                tenant_id=user.tenant_id,
                user_id=user.id,
                file_url=file_url,
                file_hash=file_hash,
                **fields,
            )
            await db.commit()
        except ConflictError as exc:
            yield {
                "type": "text",
                "content": f"⚠️ {exc.message}\n\n请到档案页查看已有记录，或修改号码后再试。",
            }
            yield {"type": "done"}
            return
        except Exception as exc:
            logger.exception("create_pending failed")
            await db.rollback()
            yield {"type": "error", "message": f"保存识别结果失败：{exc}"}
            yield {"type": "done"}
            return

        # 推 ready 侧栏（前端可立刻编辑，不必等轮询）
        payload = {
            **_serialize_invoice(inv),
            "status": "ready",
            "invoice_id": str(inv.id),
            "recognition_source": source,
        }
        yield {"type": "sidepanel", "payload": {"type": "invoice", "data": payload}}

        # 带着结构化结果让模型回复
        summary = _format_result_for_prompt(fields, source)
        reply_user = (
            f"用户上传了一张发票并说：{user_message or '请帮我识别这张发票'}。\n\n"
            f"系统已完成识别，结果如下：\n{summary}\n\n"
            f"请用简洁中文向用户汇报关键字段，提醒右侧可核对后确认归档；"
            f"对明显可疑或缺字段给出简短提示。不要编造未识别出的数字。"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": reply_user},
        ]

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
            logger.exception("LLM reply after invoice failed")
            # 至少给一段确定性摘要，避免空白
            fallback = (
                f"识别完成（来源：{'Vision' if source == 'vision' else 'OCR'}）。\n"
                f"{summary}\n\n请在右侧核对后确认归档。"
            )
            assistant_content = fallback
            yield {"type": "text", "content": fallback}
            yield {"type": "error", "message": f"AI 回复失败：{exc}"}

        if assistant_content.strip():
            await self.save_message(
                db, session_id, user.tenant_id, "assistant", assistant_content
            )
            if not session.title:
                await self.auto_title(
                    db, session, user_message or f"发票 {fields.get('invoice_number') or ''}"
                )

        yield {"type": "done"}


chat_service = ChatService()
