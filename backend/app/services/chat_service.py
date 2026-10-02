"""Chat 编排服务。

负责消息持久化、上下文组装、LLM 流式输出。
上传发票时由通用多模态大模型识别图片/文件 → 入库侧栏 → 模型带着结果回复。不使用 OCR。
"""

import logging
from typing import TYPE_CHECKING, AsyncGenerator, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_file_service import chat_file_service
from app.services.invoice_document import (
    DocumentUnreadableError,
    _as_llm_message_content,
    _extract_contract_overview,
    _guess_mime,
    _media_content,
    _prepare_document,
)
from app.services.llm_config_service import llm_config_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.session_service import session_service

if TYPE_CHECKING:
    from app.models import Message, Session, User

logger = logging.getLogger(__name__)


# 场景未配置 system_prompt 时的默认人设。
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

# 制度问答专用约束：必须优先用知识库片段，禁止编造标准
POLICY_SYSTEM_PROMPT = """你是企业财务 AI 助手，负责根据「企业知识库」回答制度/补贴/报销/合规等问题。

硬性要求：
1. 优先且仅依据下方提供的「知识库参考资料」回答具体标准、金额、流程；
2. 回答中必须写明来源文档标题（如《差旅补贴标准》）；
3. 参考资料未覆盖的内容，明确说「知识库暂无相关规定」，不要编造公司内部数字；
4. 不要用外部「国家机关参考标准」替代本公司知识库已有内容；
5. 用简洁专业的中文。
"""

# 粗粒度启发：命中则更倾向走制度问答 + RAG
_POLICY_HINTS = (
    "差旅",
    "补贴",
    "报销",
    "制度",
    "标准",
    "住宿",
    "餐补",
    "交通",
    "合规",
    "政策",
    "规定",
    "审批",
    "多少钱",
    "怎么报",
    "一线城市",
    "二线",
)


def _looks_like_policy_query(text: str) -> bool:
    """用户问题是否像制度/标准查询。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in _POLICY_HINTS)


def _format_rag_context(hits: list[dict]) -> str:
    """把召回片段格式化为可注入提示词的参考资料。"""
    parts: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = h.get("title") or "未命名文档"
        doc_type = h.get("doc_type") or ""
        score = h.get("score")
        score_s = f"{float(score):.3f}" if score is not None else "-"
        body = (h.get("content") or "").strip()
        parts.append(
            f"[{i}] 《{title}》（类型:{doc_type}，相关度:{score_s}）\n{body}"
        )
    return "\n\n".join(parts)


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
        # 归档状态与附件识别状态分开：pending_review=待归档，active=已归档
        "archive_status": "pending" if inv.status == "pending_review" else "archived" if inv.status == "active" else inv.status,
    }


def _format_result_for_prompt(fields: dict[str, Any], source: str) -> str:
    """把结构化结果写成模型可读摘要。"""
    lines = [
        f"识别来源：通用大模型",
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
        attachments: list | None = None,
    ) -> "Message":
        """持久化单条消息。attachments 与 content 同属这一条，表示一起发送的文件。"""
        from app.models import Message

        msg = Message(
            tenant_id=tenant_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            attachments=attachments,
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
        files_by_message = await chat_file_service.list_by_message_ids(
            db, [m.id for m in messages]
        )
        history: list[dict] = []
        for m in messages:
            hint = chat_file_service.prompt_hint(files_by_message.get(m.id, []))
            content = (m.content or "").strip()
            if hint:
                content = f"{content}\n{hint}".strip() if content else hint
            if content:
                history.append({"role": m.role, "content": content})
        return history

    async def _effective_system_prompt(
        self, db: AsyncSession, tenant_id: UUID | str, scene: str
    ) -> str:
        """优先用该场景用户配置的提示词；未配置或读取失败则回落默认人设。"""
        try:
            cfg = await llm_config_service.resolve(db, tenant_id, scene)
        except Exception:
            logger.exception("读取场景 %s 的 system_prompt 失败，使用默认人设", scene)
            return SYSTEM_PROMPT

        custom = (cfg or {}).get("system_prompt") if isinstance(cfg, dict) else None
        if not isinstance(custom, str):
            return SYSTEM_PROMPT
        prompt = custom.strip()
        if prompt:
            logger.info("scene=%s 使用用户配置的 system_prompt（%s 字）", scene, len(prompt))
            return prompt
        return SYSTEM_PROMPT

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
        file_id: UUID | None = None,
        file_url: str | None = None,
        file_hash: str | None = None,
        file_meta: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """流式处理用户输入，yield SSE 事件字典。

        文件上传：
        1. 推 sidepanel processing
        2. 通用大模型识别图片/文件（不使用 OCR）
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

        # 2. 解析附件行，再把文字和这条附件绑到同一条用户消息
        chat_file = await chat_file_service.resolve_for_send(
            db,
            user,
            session_id,
            file_id=file_id,
            file_url=file_url,
            file_hash=file_hash,
            file_meta=file_meta,
        )
        if chat_file is not None:
            file_url = chat_file.file_url
            file_hash = chat_file.file_hash
            file_meta = {
                "original_filename": chat_file.original_filename,
                "content_type": chat_file.content_type,
                "size": chat_file.size,
            }
        display_msg = user_message or ("（上传了文件）" if chat_file else "")
        saved = await self.save_message(
            db,
            session_id,
            user.tenant_id,
            "user",
            display_msg,
        )
        if chat_file is not None:
            await chat_file_service.bind_message(db, chat_file, saved.id)
            await chat_file_service.mark(db, chat_file.id, recognize_status="running")

        # 有附件时先语义判断，再进入对应业务，不默认当发票
        if chat_file is not None and file_url and file_hash:
            async for event in self._dispatch_upload(
                db,
                user,
                session,
                session_id,
                user_message=user_message,
                file_id=chat_file.id,
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

        # 制度问答：先检索知识库，有足够相关分则注入参考资料
        rag_hits: list[dict] = []
        try:
            rag_hits = await rag_service.retrieve(
                db,
                display_msg,
                str(user.tenant_id),
                top_k=5,
            )
        except Exception:
            logger.exception("chat RAG retrieve failed, fall back to chitchat")
            rag_hits = []

        best_score = float(rag_hits[0]["score"]) if rag_hits else 0.0
        # 相关分足够，或问题像制度查询且有任意召回
        use_policy = bool(rag_hits) and (
            best_score >= 0.35 or _looks_like_policy_query(display_msg)
        )

        if use_policy:
            scene = "policy_query"
            base_prompt = await self._effective_system_prompt(
                db, user.tenant_id, scene
            )
            # 用户自定义 prompt 时仍追加硬约束，避免忽略知识库
            if base_prompt.strip() == SYSTEM_PROMPT.strip():
                system_prompt = POLICY_SYSTEM_PROMPT
            else:
                system_prompt = (
                    f"{base_prompt.strip()}\n\n"
                    "补充约束：回答制度/标准类问题时，必须优先依据知识库参考资料，"
                    "并注明来源文档；资料不足时明确说明，禁止编造公司内部数字。"
                )
            context = _format_rag_context(rag_hits[:5])
            user_content = (
                f"【知识库参考资料】\n{context}\n\n"
                f"【用户问题】\n{display_msg}\n\n"
                "请基于参考资料作答；若资料不足以回答，请直接说明知识库暂无相关规定。"
            )
            logger.info(
                "chat policy_query rag hits=%s best_score=%.3f",
                len(rag_hits),
                best_score,
            )
        else:
            scene = "chitchat"
            system_prompt = await self._effective_system_prompt(
                db, user.tenant_id, scene
            )
            user_content = display_msg
            # 问题像制度查询但库里没命中：明确告知，避免模型瞎编外部标准冒充公司制度
            if _looks_like_policy_query(display_msg) and not rag_hits:
                system_prompt = (
                    f"{system_prompt}\n\n"
                    "用户在问企业制度/补贴标准，但当前知识库未召回相关内容。"
                    "请明确告知「知识库暂无相关制度」，可建议管理员在后台上传后重试；"
                    "不要用外部机关参考标准冒充本公司规定。"
                )

        messages = [
            {"role": "system", "content": system_prompt},
            *history[-20:],
            {"role": "user", "content": user_content},
        ]

        assistant_content = ""
        try:
            async for chunk in llm_service.stream(
                messages,
                scene=scene,
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

    async def _dispatch_upload(
        self,
        db: AsyncSession,
        user: "User",
        session: "Session",
        session_id: UUID,
        *,
        user_message: str,
        file_id: UUID,
        file_url: str,
        file_hash: str,
        file_meta: dict,
    ) -> AsyncGenerator[dict, None]:
        """先判断附件是什么，再进入发票识别、合同审查或普通对话。"""
        from app.services.invoice_vision_service import invoice_vision_service

        yield {"type": "text", "content": "正在判断这份文件…\n\n"}
        try:
            file_bytes = _download_bytes(file_url)
        except Exception as exc:
            logger.exception("download upload failed")
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": f"下载文件失败：{exc}"}
            yield {"type": "done"}
            return

        try:
            intent = await invoice_vision_service.classify(
                file_bytes,
                content_type=file_meta.get("content_type"),
                filename=file_meta.get("original_filename"),
                user_message=user_message,
                db=db,
                tenant_id=str(user.tenant_id),
            )
        except DocumentUnreadableError as exc:
            logger.info("upload has no readable body file=%s", file_meta.get("original_filename"))
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": str(exc)}
            yield {"type": "done"}
            return
        except Exception as exc:
            logger.exception("classify upload failed")
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": f"无法判断文件类型：{exc}"}
            yield {"type": "done"}
            return

        await chat_file_service.mark(db, file_id, intent=intent)

        if intent == "invoice":
            async for event in self._stream_invoice_recognize(
                db,
                user,
                session,
                session_id,
                user_message=user_message,
                file_id=file_id,
                file_url=file_url,
                file_hash=file_hash,
                file_meta=file_meta,
            ):
                yield event
            return

        if intent == "contract":
            async for event in self._stream_contract_review(
                db,
                user,
                session_id,
                user_message=user_message,
                file_id=file_id,
                file_url=file_url,
                file_hash=file_hash,
                file_bytes=file_bytes,
                filename=file_meta.get("original_filename"),
                content_type=file_meta.get("content_type"),
            ):
                yield event
            return

        async for event in self._stream_file_chat(
            db,
            user,
            session_id,
            user_message=user_message,
            file_id=file_id,
            file_bytes=file_bytes,
            filename=file_meta.get("original_filename"),
            content_type=file_meta.get("content_type"),
        ):
            yield event

    async def _stream_contract_review(
        self,
        db: AsyncSession,
        user: "User",
        session_id: UUID,
        *,
        user_message: str,
        file_id: UUID,
        file_url: str,
        file_hash: str,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
    ) -> AsyncGenerator[dict, None]:
        """合同：交给合同审查场景的模型，不走发票识别。"""
        # 和发票一样先打开右侧栏，审查结束后再换成结果
        yield {
            "type": "sidepanel",
            "payload": {
                "type": "contract",
                "data": {
                    "status": "processing",
                    "contract_name": filename,
                    "file_url": file_url,
                    "file_hash": file_hash,
                    "chat_file_id": str(file_id),
                },
            },
        }
        yield {"type": "text", "content": "这是合同，正在审查…\n\n"}
        mime = _guess_mime(file_bytes, content_type, filename)
        # 先抽正文，侧栏字段和送模共用同一份，避免模型再看到排版碎片
        try:
            _images, body_text = _prepare_document(file_bytes, mime, filename)
            if not _images and not body_text:
                raise DocumentUnreadableError(
                    "没能读出这份文件的正文，无法继续审查。"
                    "请上传未加密的 PDF 或 Word，或改用清晰的页面图片。"
                )
        except DocumentUnreadableError as exc:
            logger.info("contract has no readable body file=%s", filename)
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": str(exc)}
            yield {"type": "done"}
            return

        overview = _extract_contract_overview(body_text)
        extract_result = {
            "contract_name": filename,
            **overview,
        }
        # 先落库，侧栏字段不依赖本次 SSE；重开会话也能读到
        await chat_file_service.mark(db, file_id, extract_result=extract_result)
        logger.info(
            "contract body ready file=%s chars=%s party_a=%s amount=%s",
            filename,
            len(body_text),
            overview.get("party_a"),
            overview.get("amount"),
        )
        # 知识库规则（有向量块才注入；未索引时不阻断审查）
        rules_block = ""
        try:
            rules = await rag_service.retrieve_rules(db, str(user.tenant_id))
            if rules:
                numbered = "\n".join(f"{i + 1}. {r.strip()}" for i, r in enumerate(rules) if r.strip())
                rules_block = (
                    "\n\n以下合规规则来自企业知识库，请优先对照检查，并在结论中引用相关规则要点：\n"
                    f"{numbered}\n"
                )
                logger.info("contract review injected %s rule chunks", len(rules))
        except Exception:
            logger.exception("contract review RAG rules skipped")

        instruction = (
            "系统已经从合同文件中提取出可读正文，并放在下方。"
            "请直接用中文审查主要风险和需要关注的条款。"
            "禁止声称内容是 PDF 源码、二进制流、FlateDecode、endstream 或无法阅读；"
            "若正文较短，就基于已有条款做审查，不要讨论文件格式。"
            f"{rules_block}"
        )
        if user_message:
            instruction += f"\n用户补充：{user_message}"
        try:
            content = _media_content(file_bytes, mime, filename, instruction)
        except DocumentUnreadableError as exc:
            logger.info("contract has no readable body file=%s", filename)
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": str(exc)}
            yield {"type": "done"}
            return
        user_content = _as_llm_message_content(content)
        assistant_content = ""
        system_prompt = (
            "你是合同审查助手。用户消息里的正文已由系统从 PDF/Word 抽出，"
            "必须当作有效合同文本审查，不得拒绝或讨论文件格式。"
            "若提供了知识库合规规则，请对照规则指出风险，并区分「规则命中」与「一般法务建议」。"
            "审查完成后提醒用户在右侧核对字段并点击确认归档；"
            "不要声称已自动归档。"
        )
        try:
            async for chunk in llm_service.stream(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                scene="contract_review",
                db=db,
                tenant_id=str(user.tenant_id),
                temperature=0.2,
            ):
                assistant_content += chunk
                yield {"type": "text", "content": chunk}
        except Exception as exc:
            logger.exception("contract review failed")
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            if assistant_content.strip():
                await self.save_message(
                    db, session_id, user.tenant_id, "assistant", assistant_content
                )
            yield {
                "type": "sidepanel",
                "payload": {
                    "type": "contract",
                    "data": {
                        "status": "ready",
                        "contract_name": filename,
                        "file_url": file_url,
                        "file_hash": file_hash,
                        "chat_file_id": str(file_id),
                        **overview,
                        "review_result": {
                            "summary": f"合同审查失败：{exc}",
                            "violations": [],
                        },
                    },
                },
            }
            yield {"type": "error", "message": f"合同审查失败：{exc}"}
            yield {"type": "done"}
            return

        # 审查结果写入 pending_review，等用户点「确定归档」才变 active
        from app.services.contract_service import contract_service, infer_risk_level

        review_result = {
            "summary": assistant_content,
            "violations": [],
        }
        risk_level = infer_risk_level(review_result, None)
        contract_id: str | None = None
        archive_status = "pending"
        try:
            pending = await contract_service.create_pending(
                db,
                tenant_id=user.tenant_id,
                user_id=user.id,
                data={
                    "contract_name": overview.get("contract_name") or filename,
                    "party_a": overview.get("party_a"),
                    "party_b": overview.get("party_b"),
                    "sign_date": overview.get("sign_date"),
                    "amount": overview.get("amount"),
                    "risk_level": risk_level,
                    "review_result": review_result,
                    "file_url": file_url,
                    "file_hash": file_hash,
                },
                chat_file_id=file_id,
            )
            await db.commit()
            contract_id = str(pending.id)
            await chat_file_service.mark(
                db,
                file_id,
                recognize_status="succeeded",
                contract_id=pending.id,
                recognize_error=None,
            )
        except Exception as exc:
            logger.exception("contract create_pending failed")
            await db.rollback()
            await chat_file_service.mark(
                db, file_id, recognize_status="succeeded", recognize_error=None
            )
            # 侧栏仍可展示审查结果；无 contract_id 时走兼容确认路径
            yield {"type": "text", "content": f"\n\n（识别结果暂存失败：{exc}，请稍后重试确认归档）\n"}

        if assistant_content.strip():
            await self.save_message(
                db, session_id, user.tenant_id, "assistant", assistant_content
            )
            yield {
                "type": "sidepanel",
                "payload": {
                    "type": "contract",
                    "data": {
                        "status": "ready",
                        "file_url": file_url,
                        "file_hash": file_hash,
                        "chat_file_id": str(file_id),
                        "contract_id": contract_id,
                        "archive_status": archive_status if contract_id else None,
                        **overview,
                        "contract_name": overview.get("contract_name") or filename,
                        "risk_level": risk_level,
                        "review_result": review_result,
                    },
                },
            }
        yield {"type": "done"}

    async def _stream_file_chat(
        self,
        db: AsyncSession,
        user: "User",
        session_id: UUID,
        *,
        user_message: str,
        file_id: UUID,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
    ) -> AsyncGenerator[dict, None]:
        """普通图片或文件：附件已在表里，这里只把内容交给日常对话模型。"""
        yield {"type": "text", "content": "按普通问题处理这份文件…\n\n"}
        mime = _guess_mime(file_bytes, content_type, filename)
        try:
            content = _media_content(
                file_bytes,
                mime,
                filename,
                user_message or "请说明这份文件是什么，并回答用户可能关心的内容。",
            )
        except DocumentUnreadableError as exc:
            logger.info("file chat has no readable body file=%s", filename)
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": str(exc)}
            yield {"type": "done"}
            return
        system_prompt = await self._effective_system_prompt(
            db, user.tenant_id, "chitchat"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _as_llm_message_content(content)},
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
            logger.exception("file chat failed")
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": f"回复失败：{exc}"}
        else:
            await chat_file_service.mark(
                db, file_id, recognize_status="succeeded", recognize_error=None
            )
        if assistant_content.strip():
            await self.save_message(
                db, session_id, user.tenant_id, "assistant", assistant_content
            )
        yield {"type": "done"}

    async def _stream_invoice_recognize(
        self,
        db: AsyncSession,
        user: "User",
        session: "Session",
        session_id: UUID,
        *,
        user_message: str,
        file_id: UUID,
        file_url: str,
        file_hash: str,
        file_meta: dict,
    ) -> AsyncGenerator[dict, None]:
        """通用大模型识别图片/文件 + 侧栏 + 带结果回复。"""
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
        yield {"type": "text", "content": "正在用大模型识别发票…\n\n"}

        try:
            file_bytes = _download_bytes(file_url)
        except Exception as exc:
            logger.exception("download invoice failed")
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
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
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
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
            await chat_file_service.mark(
                db, file_id, recognize_status="succeeded", invoice_id=inv.id, recognize_error=None
            )
        except Exception as exc:
            logger.exception("create_pending failed")
            await db.rollback()
            await chat_file_service.mark(
                db, file_id, recognize_status="failed", recognize_error=str(exc)
            )
            yield {"type": "error", "message": f"保存识别结果失败：{exc}"}
            yield {"type": "done"}
            return

        # 推 ready 侧栏（前端可立刻编辑，不必等轮询）
        payload = {
            **_serialize_invoice(inv),
            "status": "ready",
            "recognize_status": "succeeded",
            "archive_status": "pending",
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
            f"回复里不要出现 OCR、光学字符识别、回落 OCR 这类字样，识别来源只说大模型。"
        )
        system_prompt = await self._effective_system_prompt(
            db, user.tenant_id, "chitchat"
        )
        messages = [
            {"role": "system", "content": system_prompt},
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
                f"识别完成（来源：通用大模型）。\n"
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
