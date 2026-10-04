"""文本意图分类：LLM 主路径，启发仅作失败回退。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from app.agent.heuristics import (
    looks_like_confirm_archive,
    looks_like_internal_reimburse,
    looks_like_official_portal_query,
    looks_like_policy_query,
    should_use_official_search,
)
from app.agent.observe import record
from app.services.llm_service import llm_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 低于此置信度时不采信模型分类，改走启发回退
MIN_INTENT_CONFIDENCE = 0.5


class Intent(str, Enum):
    """对话能力意图。附件路径仍由文件分类处理。"""

    CHITCHAT = "chitchat"
    POLICY_QUERY = "policy_query"
    PUBLIC_TAX = "public_tax"
    OFFICIAL_PORTAL = "official_portal"
    INVOICE_UPLOAD = "invoice_upload"
    CONTRACT_UPLOAD = "contract_upload"
    CONFIRM_PENDING = "confirm_pending"


class IntentSource(str, Enum):
    """分类结果来源，便于日志与评测。"""

    FILE_TYPE = "file_type"
    LLM = "llm"
    HEURISTIC = "heuristic"


@dataclass(frozen=True)
class IntentDecision:
    """一次意图判定。"""

    intent: Intent
    confidence: float
    source: IntentSource


INTENT_PROMPT = """你是财务对话的意图分类器。只输出一个 JSON 对象，不要解释、不要 Markdown。

从下面选且仅选一个 intent：
- chitchat：闲聊、自我介绍、能力说明、非财税，或无法判断
- policy_query：本公司内部制度/差旅/报销/补贴/审批流程（以企业知识库为准）
- public_tax：国家或地方公开财税政策、税率、税收优惠、总局/财政部法规、文号、新规（需权威网站检索，不是本公司制度）
- official_portal：发票真伪查验、企业工商公示、裁判文书、12366 办税等，只能引导用户去官方网站自行办理
- invoice_upload：用户想识别/归档发票，但本轮主要是在谈发票单据（无附件时请仍标此意图）
- contract_upload：用户想审查/解析合同
- confirm_pending：用户要求把当前待核对的发票或合同确认归档（如「确认归档」「帮我存进去」），不是重新识别

硬规则：
1. 问「我们公司差旅怎么报 / 住宿补贴多少」→ policy_query，即使出现「政策」「规定」。
2. 问「广州企业所得税优惠 / 增值税税率 / 财政部最新文件」→ public_tax，不要标成 policy_query。
3. 「帮我查验发票真伪 / 工商信息 / 裁判文书」→ official_portal，不要假装能查到结果，也不要标 public_tax。
4. 「确认归档 / 帮我存进去」且没有新附件 → confirm_pending。
5. 天气、问候、你是谁 → chitchat。

用户输入：{input}
附件类型：{file_type}

输出格式：{{"intent":"public_tax","confidence":0.92}}
confidence 为 0 到 1 的小数。
"""


def _parse_json_object(text: str) -> dict:
    """从模型输出中抽出 JSON 对象。"""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("模型返回空内容")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(raw[start : end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError("无法解析意图 JSON")


def _parse_intent_value(raw: object) -> Intent | None:
    """把模型 intent 字段规范成枚举。"""
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    aliases = {
        "闲聊": Intent.CHITCHAT,
        "制度问答": Intent.POLICY_QUERY,
        "公开财税": Intent.PUBLIC_TAX,
        "官方门户": Intent.OFFICIAL_PORTAL,
        "发票": Intent.INVOICE_UPLOAD,
        "合同": Intent.CONTRACT_UPLOAD,
        "确认归档": Intent.CONFIRM_PENDING,
    }
    if key in aliases:
        return aliases[key]
    try:
        return Intent(key)
    except ValueError:
        return None


def _parse_confidence(raw: object) -> float:
    """把置信度夹到 [0, 1]。缺失则视为不可靠。"""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def heuristic_intent(text: str) -> Intent:
    """LLM 不可用时的保守意图。确认归档 > 门户 > 公开财税 > 内部报销/制度 > 闲聊。"""
    if looks_like_confirm_archive(text):
        return Intent.CONFIRM_PENDING
    if looks_like_official_portal_query(text):
        return Intent.OFFICIAL_PORTAL
    if should_use_official_search(text):
        return Intent.PUBLIC_TAX
    if looks_like_internal_reimburse(text) or looks_like_policy_query(text):
        return Intent.POLICY_QUERY
    return Intent.CHITCHAT


def _decision(intent: Intent, confidence: float, source: IntentSource) -> IntentDecision:
    """构造判定并打日志。"""
    logger.info(
        "intent=%s confidence=%.3f source=%s",
        intent.value,
        confidence,
        source.value,
    )
    return IntentDecision(intent=intent, confidence=confidence, source=source)


async def classify_intent(
    input_text: str,
    *,
    file_type: str | None = None,
    db: "AsyncSession | None" = None,
    tenant_id: str | None = None,
) -> IntentDecision:
    """识别用户文本意图。

    附件已由 ChatService 走文件分类；此处 file_type 仅给骨架编排预留短路。
    """
    if file_type == "invoice":
        decision = _decision(Intent.INVOICE_UPLOAD, 1.0, IntentSource.FILE_TYPE)
    elif file_type == "contract":
        decision = _decision(Intent.CONTRACT_UPLOAD, 1.0, IntentSource.FILE_TYPE)
    else:
        text = (input_text or "").strip()
        if not text:
            decision = _decision(Intent.CHITCHAT, 1.0, IntentSource.HEURISTIC)
        else:
            prompt = INTENT_PROMPT.format(input=text, file_type=file_type or "none")
            decision = None
            try:
                result = await llm_service.invoke(
                    messages=[{"role": "user", "content": prompt}],
                    scene="chitchat",
                    db=db,
                    tenant_id=tenant_id,
                    temperature=0.0,
                    max_tokens=256,
                    apply_scene_prompt=False,
                )
                data = _parse_json_object(result)
                intent = _parse_intent_value(data.get("intent"))
                confidence = _parse_confidence(data.get("confidence"))
                if intent is not None and confidence >= MIN_INTENT_CONFIDENCE:
                    decision = _decision(intent, confidence, IntentSource.LLM)
                else:
                    logger.info(
                        "intent llm rejected intent=%s confidence=%.3f, fallback heuristic",
                        None if intent is None else intent.value,
                        confidence,
                    )
            except Exception:
                logger.exception("intent llm classify failed, fallback heuristic")
            if decision is None:
                decision = _decision(heuristic_intent(text), 0.0, IntentSource.HEURISTIC)

    record(
        "classify_intent",
        intent=decision.intent.value,
        source=decision.source.value,
        confidence=decision.confidence,
        tenant_id=tenant_id or "",
        text=(input_text or "")[:80],
    )
    return decision


async def route_intent(
    input_text: str,
    file_type: str | None = None,
    db: "AsyncSession | None" = None,
    tenant_id: str | None = None,
) -> Intent:
    """兼容骨架编排：只返回意图枚举。"""
    decision = await classify_intent(
        input_text,
        file_type=file_type,
        db=db,
        tenant_id=tenant_id,
    )
    return decision.intent
