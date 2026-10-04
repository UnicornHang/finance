"""意图分类：解析 LLM JSON，失败时回退启发。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.router import (
    Intent,
    IntentSource,
    classify_intent,
    route_intent,
)


@pytest.mark.asyncio
async def test_classify_uses_llm_json():
    """有效 JSON 且置信度足够时采信模型。"""
    with patch("app.agent.router.llm_service") as mock_llm:
        mock_llm.invoke = AsyncMock(
            return_value='{"intent":"public_tax","confidence":0.91}'
        )
        decision = await classify_intent("广州企业所得税优惠有哪些？")
    assert decision.intent == Intent.PUBLIC_TAX
    assert decision.source == IntentSource.LLM
    assert decision.confidence == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_classify_strips_markdown_fence():
    """容忍模型用代码围栏包 JSON。"""
    with patch("app.agent.router.llm_service") as mock_llm:
        mock_llm.invoke = AsyncMock(
            return_value='```json\n{"intent":"policy_query","confidence":0.8}\n```'
        )
        decision = await classify_intent("差旅住宿补贴怎么报？")
    assert decision.intent == Intent.POLICY_QUERY
    assert decision.source == IntentSource.LLM


@pytest.mark.asyncio
async def test_classify_low_confidence_falls_back_heuristic():
    """置信度过低时不采信模型。"""
    with patch("app.agent.router.llm_service") as mock_llm:
        mock_llm.invoke = AsyncMock(
            return_value='{"intent":"chitchat","confidence":0.12}'
        )
        decision = await classify_intent("广州最新财务税收政策是怎样的？")
    assert decision.intent == Intent.PUBLIC_TAX
    assert decision.source == IntentSource.HEURISTIC


@pytest.mark.asyncio
async def test_classify_invalid_json_falls_back_heuristic():
    """演示模式或非 JSON 输出走启发。"""
    with patch("app.agent.router.llm_service") as mock_llm:
        mock_llm.invoke = AsyncMock(return_value="（演示模式）收到：天气")
        decision = await classify_intent("帮我查验这张发票真伪")
    assert decision.intent == Intent.OFFICIAL_PORTAL
    assert decision.source == IntentSource.HEURISTIC


@pytest.mark.asyncio
async def test_file_type_short_circuits_llm():
    """已知附件类型不再调用分类模型。"""
    with patch("app.agent.router.llm_service") as mock_llm:
        mock_llm.invoke = AsyncMock()
        decision = await classify_intent("看看这个", file_type="invoice")
        mock_llm.invoke.assert_not_called()
    assert decision.intent == Intent.INVOICE_UPLOAD
    assert decision.source == IntentSource.FILE_TYPE


@pytest.mark.asyncio
async def test_route_intent_returns_enum():
    """骨架编排仍拿到 Intent 枚举。"""
    with patch("app.agent.router.llm_service") as mock_llm:
        mock_llm.invoke = AsyncMock(
            return_value='{"intent":"chitchat","confidence":0.99}'
        )
        intent = await route_intent("你好")
    assert intent == Intent.CHITCHAT
