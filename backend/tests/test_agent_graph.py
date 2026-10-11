"""LangGraph 文本图：白名单、软提醒、拒绝非法工具。"""

import pytest

pytest.importorskip("langgraph")

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool

from app.agent.graph import after_agent, after_gate, get_text_graph, graph_runtime, tools_node
from app.agent.llm_adapter import ChatFinanceLLM
from app.agent.policy import TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL
from app.agent.router import Intent


class _FakeLLM:
    """固定返回同一条 AIMessage。"""

    def __init__(self, message: AIMessage):
        self.message = message
        self.calls = 0

    async def ainvoke(self, messages, *, tools=None, temperature=None):
        self.calls += 1
        return self.message


class _SequencedLLM:
    """按调用次序返回不同 AIMessage。"""

    def __init__(self, messages: list[AIMessage]):
        self.messages = messages
        self.calls = 0

    async def ainvoke(self, messages, *, tools=None, temperature=None):
        idx = min(self.calls, len(self.messages) - 1)
        self.calls += 1
        return self.messages[idx]


def _query_tool(mock: AsyncMock, result: str) -> StructuredTool:
    """真实 coroutine，避免 StructuredTool 解析 AsyncMock。"""

    async def query_policy(question: str) -> str:
        await mock(question)
        return result

    return StructuredTool.from_function(
        coroutine=query_policy,
        name=TOOL_QUERY_POLICY,
        description="查询企业制度",
    )


def _search_tool(mock: AsyncMock, result: str) -> StructuredTool:
    """真实 coroutine，供白名单测试。"""

    async def search_official_data(
        query: str,
        region: str | None = None,
        period: str | None = None,
        topic: str | None = None,
    ) -> str:
        await mock(query, region=region, period=period, topic=topic)
        return result

    return StructuredTool.from_function(
        coroutine=search_official_data,
        name=TOOL_SEARCH_OFFICIAL,
        description="检索公开财税",
    )


@pytest.mark.asyncio
async def test_graph_forces_policy_tool_when_model_skips():
    """制度问题未调工具时，用本轮原话补查知识库，不再空检索放行。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "《差旅》住宿 500"),
        _search_tool(search_mock, "总局公告"),
    ]
    llm = _FakeLLM(AIMessage(content="我直接答", tool_calls=[]))
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    question = "差旅住宿补贴怎么报？"
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.POLICY_QUERY.value,
                "display_msg": question,
                "messages": [HumanMessage(content=question)],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert llm.calls == 1
    assert "住宿 500" in (final.get("tool_result") or "")
    query_mock.assert_awaited_once_with(question)
    search_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_forces_official_search_for_followup():
    """公开财税追问未调工具时，按本轮原话检索，不沿用上一轮检索词。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内"),
        _search_tool(search_mock, "总局公告"),
    ]
    llm = _FakeLLM(AIMessage(content="我直接答", tool_calls=[]))
    question = "2026年福建省一季度财报"
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": question,
                "messages": [
                    HumanMessage(content="广东省2026年一季度财报"),
                    AIMessage(content="全国一般公共预算收入61613亿元"),
                    HumanMessage(content=question),
                ],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert llm.calls == 1
    assert "总局公告" in (final.get("tool_result") or "")
    search_mock.assert_awaited_once_with(
        question, region=None, period=None, topic=None
    )
    query_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_drops_stale_slots_from_previous_turn():
    """模型若带上上一轮地区，检索词和槽位仍以本轮原话为准。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内"),
        _search_tool(search_mock, "福建资料"),
    ]
    question = "2026年福建省一季度财报"
    llm = _FakeLLM(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "s1",
                    "name": TOOL_SEARCH_OFFICIAL,
                    "args": {
                        "query": "广东省2026年一季度财政收支",
                        "region": "广东省",
                        "period": "2026年一季度",
                        "topic": "财政收支",
                    },
                }
            ],
        )
    )
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": question,
                "messages": [HumanMessage(content=question)],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert "福建资料" in (final.get("tool_result") or "")
    search_mock.assert_awaited_once_with(
        question, region=None, period=None, topic=None
    )
    query_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_keeps_slots_that_appear_in_current_question():
    """本轮原话里写明的地区、期间、主题仍然传给检索。"""
    search_mock = AsyncMock()
    bound = [_search_tool(search_mock, "广东资料")]
    question = "广东省2026年一季度财报"
    llm = _FakeLLM(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "s1",
                    "name": TOOL_SEARCH_OFFICIAL,
                    "args": {
                        "query": "全国财政收支",
                        "region": "广东省",
                        "period": "2026年一季度",
                        "topic": "财报",
                    },
                }
            ],
        )
    )
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": question,
                "messages": [HumanMessage(content=question)],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    search_mock.assert_awaited_once_with(
        question,
        region="广东省",
        period="2026年一季度",
        topic="财报",
    )


@pytest.mark.asyncio
async def test_graph_policy_intent_can_call_official_tool():
    """制度意图白名单含官方工具，模型可主动调用。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内制度"),
        _search_tool(search_mock, "外网政策"),
    ]
    llm = _FakeLLM(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "x",
                    "name": TOOL_SEARCH_OFFICIAL,
                    "args": {"query": "税率"},
                }
            ],
        )
    )
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.POLICY_QUERY.value,
                "display_msg": "税率政策与公司衔接",
                "messages": [HumanMessage(content="税率政策与公司衔接")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    search_mock.assert_awaited()
    assert "外网政策" in (final.get("tool_result") or "")


@pytest.mark.asyncio
async def test_graph_runs_both_tools_in_one_round():
    """同轮合法双工具均执行。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内制度"),
        _search_tool(search_mock, "官方资料"),
    ]
    llm = _FakeLLM(
        AIMessage(
            content="",
            tool_calls=[
                {"id": "1", "name": TOOL_QUERY_POLICY, "args": {"question": "报销"}},
                {"id": "2", "name": TOOL_SEARCH_OFFICIAL, "args": {"query": "留抵退税"}},
            ],
        )
    )
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": "留抵退税我们公司怎么报销",
                "messages": [HumanMessage(content="留抵退税我们公司怎么报销")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    query_mock.assert_awaited()
    search_mock.assert_awaited()
    result = final.get("tool_result") or ""
    assert "库内制度" in result
    assert "官方资料" in result


def test_after_gate_skips_agent_without_tools():
    assert after_gate({"allowed_tools": []}) == "finalize"
    assert after_gate({"allowed_tools": [TOOL_QUERY_POLICY]}) == "agent"


def test_after_agent_routes_pending():
    assert after_agent({"pending_calls": [{"name": "x"}]}) == "tools"
    assert after_agent({"pending_calls": []}) == "finalize"


@pytest.mark.asyncio
async def test_tools_node_skips_name_not_in_allowlist():
    """二次校验：不在白名单的工具不执行。"""
    search_mock = AsyncMock()
    bound = [_search_tool(search_mock, "外网")]
    token = graph_runtime.set(
        {"llm": MagicMock(spec=ChatFinanceLLM), "bound_tools": bound}
    )
    try:
        out = await tools_node(
            {
                "allowed_tools": [TOOL_QUERY_POLICY],
                "pending_calls": [
                    {"id": "1", "name": TOOL_SEARCH_OFFICIAL, "args": {"query": "税"}}
                ],
                "display_msg": "税",
                "messages": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    search_mock.assert_not_awaited()
    assert out["tool_result"] == ""
