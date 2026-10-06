"""人工触发：按原件重新跑合同审查并写回档案。

聊天首轮走 SSE 流式输出；侧栏「重新审查」是同步 HTTP，提示词与首轮对齐。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.services.chat_file_service import chat_file_service
from app.services.contract_service import contract_service, infer_risk_level
from app.services.invoice_document import (
    DocumentUnreadableError,
    _as_llm_message_content,
    _extract_contract_overview,
    _guess_mime,
    _media_content,
    _prepare_document,
)
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.storage_service import storage_service

if TYPE_CHECKING:
    from app.models import Contract, User

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM_PROMPT = (
    "你是合同审查助手。用户消息里的正文已由系统从 PDF/Word 抽出，"
    "必须当作有效合同文本审查，不得拒绝或讨论文件格式。"
    "若提供了知识库合规规则，请对照规则指出风险，并区分「规则命中」与「一般法务建议」。"
    "审查完成后提醒用户在右侧核对字段并点击确认归档；"
    "不要声称已自动归档。"
)


async def rereview_contract(
    db: AsyncSession,
    user: "User",
    contract_id: UUID,
) -> "Contract":
    """下载原件 → 抽正文 → 模型审查 → 覆盖当前合同记录。"""
    row = await contract_service.get(db, user.tenant_id, contract_id, user=user)
    if not row.file_url:
        raise BusinessError("没有原件，无法重新审查", code="CONTRACT_FILE_MISSING")

    chat_file = await chat_file_service.latest_for_contract(db, row.id)
    filename = (
        chat_file.original_filename
        if chat_file and chat_file.original_filename
        else (row.contract_name or row.file_url.rsplit("/", 1)[-1])
    )
    content_type = chat_file.content_type if chat_file else None

    try:
        file_bytes = storage_service.download_bytes(row.file_url)
    except Exception as exc:
        raise BusinessError(f"下载原件失败：{exc}", code="CONTRACT_FILE_DOWNLOAD") from exc

    mime = _guess_mime(file_bytes, content_type, filename)
    try:
        _images, body_text = _prepare_document(file_bytes, mime, filename)
        if not _images and not body_text:
            raise DocumentUnreadableError(
                "没能读出这份文件的正文，无法继续审查。"
                "请上传未加密的 PDF 或 Word，或改用清晰的页面图片。"
            )
    except DocumentUnreadableError as exc:
        raise BusinessError(str(exc), code="DOCUMENT_UNREADABLE") from exc

    overview = _extract_contract_overview(body_text)
    rules_block = await _rules_block(db, str(user.tenant_id))
    instruction = (
        "系统已经从合同文件中提取出可读正文，并放在下方。"
        "请直接用中文审查主要风险和需要关注的条款。"
        "禁止声称内容是 PDF 源码、二进制流、FlateDecode、endstream 或无法阅读；"
        "若正文较短，就基于已有条款做审查，不要讨论文件格式。"
        f"{rules_block}"
    )
    try:
        content = _media_content(file_bytes, mime, filename, instruction)
    except DocumentUnreadableError as exc:
        raise BusinessError(str(exc), code="DOCUMENT_UNREADABLE") from exc

    try:
        summary = await llm_service.invoke(
            [
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": _as_llm_message_content(content)},
            ],
            scene="contract_review",
            db=db,
            tenant_id=str(user.tenant_id),
            temperature=0.2,
            apply_scene_prompt=False,
        )
    except Exception as exc:
        raise BusinessError(f"重新审查失败：{exc}", code="CONTRACT_REVIEW_FAILED") from exc

    if not (summary or "").strip():
        raise BusinessError("模型未返回审查结果，请稍后重试", code="CONTRACT_REVIEW_EMPTY")

    review_result = {"summary": summary, "violations": []}
    risk_level = infer_risk_level(review_result, None)
    updated = await contract_service.refresh_review(
        db,
        tenant_id=user.tenant_id,
        user=user,
        contract_id=row.id,
        data={
            "contract_name": overview.get("contract_name") or filename,
            "party_a": overview.get("party_a"),
            "party_b": overview.get("party_b"),
            "sign_date": overview.get("sign_date"),
            "amount": overview.get("amount"),
            "risk_level": risk_level,
            "review_result": review_result,
            "file_url": row.file_url,
            "file_hash": row.file_hash,
        },
        chat_file_id=chat_file.id if chat_file else None,
    )
    if chat_file is not None:
        await chat_file_service.mark(
            db,
            chat_file.id,
            recognize_status="succeeded",
            recognize_error=None,
            extract_result={"contract_name": filename, **overview},
            contract_id=updated.id,
        )
    logger.info("contract rereviewed id=%s risk=%s", updated.id, updated.risk_level)
    return updated


async def _rules_block(db: AsyncSession, tenant_id: str) -> str:
    """知识库规则注入；失败时不阻断审查。"""
    try:
        rules = await rag_service.retrieve_rules(db, tenant_id)
        if not rules:
            return ""
        numbered = "\n".join(f"{i + 1}. {r.strip()}" for i, r in enumerate(rules) if r.strip())
        return (
            "\n\n以下合规规则来自企业知识库，请优先对照检查，并在结论中引用相关规则要点：\n"
            f"{numbered}\n"
        )
    except Exception:
        logger.exception("contract rereview RAG rules skipped")
        return ""
