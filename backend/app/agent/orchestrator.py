"""文本 Agent 编排：LangGraph 跑工具循环，再流式生成。"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, AsyncGenerator, Never
from uuid import UUID

from app.agent.context import SessionContext, attach_memory
from app.agent.graph import get_text_graph, graph_runtime
from app.agent.llm_adapter import ChatFinanceLLM, history_to_messages
from app.agent.memory import set_last_intent
from app.agent.memory.assemble import assemble_context
from app.agent.memory.entities import remember_policy_title
from app.agent.observe import record
from app.agent.policy import (
    TOOL_SEARCH_OFFICIAL,
    status_event_for_tools,
    tools_for_intent,
)
from app.agent.router import Intent
from app.agent.tools.catalog import build_text_tools, persistable_tool_calls, pick_tools
from app.agent.upload_graph import get_upload_graph, upload_runtime
from app.services.chat_file_service import chat_file_service
from app.services.invoice_vision_service import invoice_vision_service
from app.services.stream_persist import StreamPersistResult, stream_llm_and_persist

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Session, User
    from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"《([^》]+)》")


class AgentOrchestrator:
    """无附件文本走 LangGraph；不持有跨请求状态。"""

    async def stream_text(
        self,
        service: "ChatService",
        db: "AsyncSession",
        user: "User",
        session: "Session",
        session_id: UUID,
        *,
        display_msg: str,
        history: list[dict],
        intent: Intent,
        ctx: SessionContext | None = None,
        related_history: str = "",
    ) -> AsyncGenerator[dict, None]:
        """跑图后把最终回复流式输出为 SSE dict。"""
        if intent == Intent.CONFIRM_PENDING:
            async for event in service._stream_confirm_pending(
                db, user, session_id, display_msg=display_msg, ctx=ctx
            ):
                yield event
            return

        allowed = tools_for_intent(intent)
        status = status_event_for_tools(allowed)
        if status:
            yield status

        system_prompt, user_content, scene = await self._opening_prompt(
            service, db, user, intent, display_msg
        )
        messages = history_to_messages(
            history, attach_memory(system_prompt, ctx, related_history), user_content
        )
        trace: dict[str, Any] = {}
        all_tools = build_text_tools(db, str(user.tenant_id), trace)
        bound = pick_tools(all_tools, allowed)
        llm = ChatFinanceLLM(
            scene="chitchat" if scene == "chitchat" else scene,
            db=db,
            tenant_id=str(user.tenant_id),
            session_id=str(session_id),
            user_id=str(user.id),
        )
        graph = get_text_graph()
        token = graph_runtime.set({"llm": llm, "bound_tools": bound})
        try:
            final = await graph.ainvoke(
                {
                    "intent": intent.value,
                    "display_msg": display_msg,
                    "messages": messages,
                    "allowed_tools": allowed,
                    "tool_round": 0,
                    "pending_calls": [],
                    "tool_result": "",
                }
            )
        finally:
            graph_runtime.reset(token)
        tool_result = (final.get("tool_result") or "").strip()
        openai_messages, scene = await self._closing_messages(
            service,
            db,
            user,
            intent,
            display_msg,
            history,
            tool_result,
            system_prompt,
            user_content,
            ctx,
            related_history,
        )
        record(
            "llm_scene",
            intent=intent.value,
            scene=scene,
            tenant_id=str(user.tenant_id),
        )
        search_trace = persistable_tool_calls(trace)
        search_block = None
        if isinstance(search_trace, dict):
            search_block = search_trace.get("search") or (
                search_trace
                if search_trace.get("tool") == TOOL_SEARCH_OFFICIAL
                else None
            )
        if isinstance(search_block, dict):
            raw_sources = search_block.get("sources") or []
            if isinstance(raw_sources, list) and raw_sources:
                yield {
                    "type": "sources",
                    "hit_count": int(search_block.get("hit_count") or len(raw_sources)),
                    "sources": raw_sources,
                }

        # 助手消息只由封装落一条；出错或中断后不再发 done
        persist = StreamPersistResult()
        stream_failed = False
        async for event in stream_llm_and_persist(
            save_message=service.save_message,
            db=db,
            session_id=session_id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            messages=openai_messages,
            scene=scene,
            base_tool_calls=search_trace,
            result=persist,
            error_prefix="AI 调用失败",
        ):
            if event.get("type") == "error":
                stream_failed = True
            yield event

        if persist.interrupted or stream_failed:
            return

        if persist.saved and persist.content.strip():
            if not history or len(history) <= 1:
                await service.auto_title(db, session, display_msg)
            title = _first_policy_title(tool_result)
            if intent == Intent.POLICY_QUERY and title:
                await remember_policy_title(db, session_id, title)
        yield {"type": "done"}

    async def _opening_prompt(
        self,
        service: "ChatService",
        db: "AsyncSession",
        user: "User",
        intent: Intent,
        display_msg: str,
    ) -> tuple[str, str, str]:
        """图运行前的 system / user / scene。"""
        from app.services.chat_service import (
            POLICY_SYSTEM_PROMPT,
            PORTAL_SYSTEM_PROMPT,
            PUBLIC_TAX_SYSTEM_PROMPT,
            current_date_instruction,
        )

        match intent:
            case Intent.INVOICE_UPLOAD | Intent.CONTRACT_UPLOAD:
                kind = "发票" if intent == Intent.INVOICE_UPLOAD else "合同"
                system_prompt = await service._effective_system_prompt(
                    db, user.tenant_id, "chitchat"
                )
                user_content = (
                    f"{display_msg}\n\n"
                    f"用户想处理{kind}但本轮没有附件。"
                    f"请引导对方在对话框上传{kind}文件后再继续，不要假装已经识别或审查完成。"
                )
                return system_prompt, user_content, "chitchat"
            case Intent.OFFICIAL_PORTAL:
                user_content = (
                    f"{display_msg}\n\n"
                    "请引导用户前往对应官方平台自行办理，并给出准确网站名称与网址："
                    "全国增值税发票查验平台 https://inv-veri.chinatax.gov.cn ；"
                    "国家企业信用信息公示系统 https://www.gsxt.gov.cn ；"
                    "中国裁判文书网 https://wenshu.court.gov.cn ；"
                    "12366 纳税服务平台 https://12366.chinatax.gov.cn 。"
                    "不要假装已经完成查验。"
                )
                return PORTAL_SYSTEM_PROMPT, user_content, "chitchat"
            case Intent.POLICY_QUERY:
                return (
                    POLICY_SYSTEM_PROMPT,
                    (
                        f"{current_date_instruction()}\n\n"
                        f"{display_msg}\n\n"
                        "本轮必须针对上面的用户原话调用 query_policy；"
                        "若同时涉及国家或地方公开数据，再调用 search_official_data，query 也用用户原话。"
                        "上文回答过同类问题也不能跳过，禁止复用上一轮的检索词。"
                        "region/period/topic 只填本轮原话里出现的信息。"
                        "若知识库暂无规定，明确告知，禁止用外网冒充公司制度。"
                    ),
                    "policy_query",
                )
            case Intent.PUBLIC_TAX:
                return (
                    PUBLIC_TAX_SYSTEM_PROMPT,
                    (
                        f"{current_date_instruction()}\n\n"
                        f"{display_msg}\n\n"
                        "本轮必须针对上面的用户原话调用 search_official_data，"
                        "query 用用户原话；上文回答过同类问题也不能跳过。"
                        "禁止复用上一轮的检索词、地区或财政数字。"
                        "region/period/topic 只填本轮原话里出现的信息。"
                        "需要对照本公司口径时再调用 query_policy。"
                        "不要在未调用工具时直接给出税率、文号或财政数字。"
                    ),
                    "chitchat",
                )
            case Intent.CHITCHAT | Intent.CONFIRM_PENDING:
                system_prompt = await service._effective_system_prompt(
                    db, user.tenant_id, "chitchat"
                )
                return system_prompt, display_msg, "chitchat"
            case _:
                unreachable: Never = intent
                raise ValueError(f"unhandled intent: {unreachable}")

    async def _closing_messages(
        self,
        service: "ChatService",
        db: "AsyncSession",
        user: "User",
        intent: Intent,
        display_msg: str,
        history: list[dict],
        tool_result: str,
        opening_system: str,
        opening_user: str,
        ctx: SessionContext | None = None,
        related_history: str = "",
    ) -> tuple[list[dict], str]:
        """根据工具结果组装最终流式消息（与 A 管道约束对齐）。"""
        from app.services.chat_service import (
            POLICY_SYSTEM_PROMPT,
            PUBLIC_TAX_SYSTEM_PROMPT,
            current_date_instruction,
        )

        def _source_flags(text: str) -> tuple[bool, bool]:
            """粗分知识库块与官方块是否出现。"""
            body = text or ""
            has_policy = (
                "相关度:" in body
                or ("《" in body and "知识库暂无" not in body[:80])
                or "知识库暂无" in body
            )
            has_official = any(
                marker in body
                for marker in (
                    "权威官网",
                    "权威站点",
                    "专业参考平台",
                    "【原文",
                    "未在财政部",
                    "不得编造",
                )
            )
            return has_policy, has_official

        def _policy_usable(text: str) -> bool:
            """知识库是否有可引用正文（非空库提示）。"""
            if not text:
                return False
            if "知识库暂无" in text and "相关度:" not in text:
                return False
            return "相关度:" in text or "《" in text

        _citation_rule = (
            "公开网页资料按 [1][2]… 编号，企业制度资料按 【制度1】【制度2】… 编号；"
            "回答中对关键数字、文号、结论请标注对应编号；"
            "公开数据优先采信标注为权威官网的条目；禁止编造资料中未出现的数字。"
        )

        def _official_usable(text: str) -> bool:
            """官方检索是否有可引用命中。"""
            if not text:
                return False
            if "未检索到" in text or "检索失败" in text or "未在财政部" in text:
                if "权威官网" not in text and "公开网页摘要" not in text:
                    return False
            return any(
                m in text
                for m in (
                    "权威官网",
                    "专业参考平台",
                    "公开网页摘要",
                    "【原文",
                    "链接:",
                )
            )

        match intent:
            case Intent.POLICY_QUERY | Intent.PUBLIC_TAX:
                has_policy, has_official = _source_flags(tool_result)
                policy_ok = _policy_usable(tool_result)
                official_ok = _official_usable(tool_result)

                if policy_ok and official_ok:
                    primary = (
                        "先回应用户主诉求，再补充对照；"
                        "禁止把官方标准说成「本公司规定」，也禁止把公司制度说成国家法规。"
                    )
                    if intent == Intent.PUBLIC_TAX:
                        system_prompt = PUBLIC_TAX_SYSTEM_PROMPT
                        scene = "chitchat"
                        lead = (
                            "请用「我联网查了公开网页，并优先采信权威官方来源」自然过渡，"
                            "再按核心摘要 → 目标与变化 / 范围与时间 / 具体任务 / 影响与建议 作答；"
                            "关键文号、条款、网站名和链接加粗；结尾开放追问，并附温馨提示免责声明。"
                            "本轮数字、文号和链接只能来自本次检索资料，"
                            "禁止把对话历史里的财政数字挪用来回答本轮问题。"
                        )
                    else:
                        system_prompt = POLICY_SYSTEM_PROMPT
                        scene = "policy_query"
                        lead = "请基于资料作答；公司执行口径以知识库为准。"
                    user_content = (
                        f"{current_date_instruction()}\n\n"
                        f"【检索资料（可能含企业制度与权威网站）】\n{tool_result}\n\n"
                        f"【用户问题】\n{display_msg}\n\n"
                        f"{lead}{primary}\n{_citation_rule}"
                    )
                elif policy_ok:
                    system_prompt = POLICY_SYSTEM_PROMPT
                    user_content = (
                        f"【知识库参考资料】\n{tool_result}\n\n"
                        f"【用户问题】\n{display_msg}\n\n"
                        "请基于参考资料作答；若资料不足以回答，请直接说明知识库暂无相关规定。"
                        "不要把外部机关标准冒充本公司规定。"
                    )
                    scene = "policy_query"
                elif official_ok:
                    system_prompt = PUBLIC_TAX_SYSTEM_PROMPT
                    user_content = (
                        f"{current_date_instruction()}\n\n"
                        f"【权威网站检索资料】\n{tool_result}\n\n"
                        f"【用户问题】\n{display_msg}\n\n"
                        "请用「我联网查了公开网页，并优先采信权威官方来源」自然过渡，再按"
                        "核心摘要 → 目标与变化 / 范围与时间 / 具体任务 / 影响与建议 作答；"
                        "关键文号、条款、网站名和链接加粗；结尾开放追问，并附温馨提示免责声明。"
                        "本轮数字、文号和链接只能来自本次检索资料，"
                        "禁止把对话历史里的财政数字挪用来回答本轮问题。"
                        "若用户还问本公司制度而资料中没有，明确说明未查到公司制度。"
                        "资料里若已有全国一般公共预算等数字，必须引用，禁止声称尚未公布；"
                        "不要用地市财政局材料冒充全国数据。"
                        f"\n{_citation_rule}"
                    )
                    scene = "chitchat"
                else:
                    system_prompt = await service._effective_system_prompt(
                        db, user.tenant_id, "chitchat"
                    )
                    if intent == Intent.POLICY_QUERY and (
                        has_policy or not tool_result
                    ):
                        system_prompt = (
                            f"{system_prompt}\n\n"
                            "用户在问企业制度/补贴标准，但当前知识库未召回足够相关内容。"
                            "请明确告知「知识库暂无相关制度」，可建议管理员在后台上传后重试；"
                            "不要用外部机关参考标准冒充本公司规定。"
                        )
                    else:
                        system_prompt = (
                            f"{system_prompt}\n\n"
                            f"{current_date_instruction()}\n"
                            "本轮未取得可用的企业制度或权威网站资料。"
                            "请明确告知暂无可靠检索结果，禁止编造税率、文号、财政数字或公司规定。"
                            "禁止使用「我联网查了公开网页」的口吻，"
                            "禁止把对话历史里的数字、文号复述为本轮结论。"
                            "不要臆测「数据尚未发布」——除非检索资料里明确写了发布时间或未公布说明；"
                            "可给出财政部、中国政府网等可自行查阅的入口。"
                        )
                    user_content = (
                        f"{display_msg}\n\n"
                        "本轮没有检索到可用资料。请直接说明暂无可靠结果，"
                        "不要声称已经联网，也不要复述上文中的财政数字或文号。"
                    )
                    scene = "chitchat"
            case (
                Intent.CHITCHAT
                | Intent.OFFICIAL_PORTAL
                | Intent.INVOICE_UPLOAD
                | Intent.CONTRACT_UPLOAD
                | Intent.CONFIRM_PENDING
            ):
                system_prompt = opening_system
                user_content = opening_user
                scene = "chitchat"
            case _:
                unreachable: Never = intent
                raise ValueError(f"unhandled intent: {unreachable}")

        return (
            [
                {"role": "system", "content": attach_memory(system_prompt, ctx, related_history)},
                *history,
                {"role": "user", "content": user_content},
            ],
            scene,
        )

    async def stream_upload(
        self,
        service: "ChatService",
        db: "AsyncSession",
        user: "User",
        session: "Session",
        session_id: UUID,
        *,
        user_message: str,
        file_id: UUID,
        file_url: str,
        file_hash: str,
        file_meta: dict,
        exclude_message_id: UUID,
    ) -> AsyncGenerator[dict, None]:
        """附件子图分类后，调用现有识别/审查/文件闲聊并流式 SSE。"""
        try:
            hit = await service.lookup_archived_upload(db, user, file_hash)
            if hit is not None:
                kind, row = hit
                record(
                    "upload_archived_reuse",
                    file_kind=kind,
                    tenant_id=str(user.tenant_id),
                )
                async for event in service._stream_archived_reuse(
                    db, user, session_id, file_id=file_id, kind=kind, row=row
                ):
                    yield event
                return

            # 避免与 ChatService 模块循环：下载函数定义在 chat_service
            from app.services.chat_service import _download_bytes

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

            token = upload_runtime.set(
                {
                    "classify": invoice_vision_service.classify,
                    "file_bytes": file_bytes,
                    "content_type": file_meta.get("content_type"),
                    "filename": file_meta.get("original_filename"),
                    "user_message": user_message,
                    "db": db,
                    "tenant_id": str(user.tenant_id),
                }
            )
            try:
                final = await get_upload_graph().ainvoke(
                    {"user_message": user_message or "", "file_kind": "", "error": ""}
                )
            finally:
                upload_runtime.reset(token)

            kind = final.get("file_kind") or "chat"
            error = (final.get("error") or "").strip()
            if kind == "error":
                await chat_file_service.mark(
                    db, file_id, recognize_status="failed", recognize_error=error
                )
                yield {"type": "error", "message": error}
                yield {"type": "done"}
                return

            await chat_file_service.mark(db, file_id, intent=kind)
            mapped = {
                "invoice": Intent.INVOICE_UPLOAD.value,
                "contract": Intent.CONTRACT_UPLOAD.value,
            }
            await set_last_intent(
                db, session_id, mapped.get(kind, Intent.CHITCHAT.value)
            )
            record(
                "upload_route",
                file_kind=kind,
                tenant_id=str(user.tenant_id),
            )

            match kind:
                case "invoice":
                    async for event in service._stream_invoice_recognize(
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
                case "contract":
                    async for event in service._stream_contract_review(
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
                case _:
                    async for event in service._stream_file_chat(
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
        finally:
            # 只为折叠窗口外摘要；不把 history 传给识别、审查或文件闲聊
            await assemble_context(db, session_id, exclude_message_id, session)


def _first_policy_title(tool_result: str) -> str:
    """从知识库工具结果里取第一个书名号标题。"""
    match = _TITLE_RE.search(tool_result or "")
    return match.group(1).strip() if match else ""


agent_orchestrator = AgentOrchestrator()
