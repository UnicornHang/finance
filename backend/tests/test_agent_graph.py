"""LangGraph 文本图：白名单、软提醒、拒绝非法工具。"""

import pytest

pytest.importorskip("langgraph")

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
async def test_graph_soft_remind_then_empty_when_still_no_tool():
    """首轮无 call 时软提醒；第二次仍无 call 则空结果，不强制执行工具。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "《差旅》住宿 500"),
        _search_tool(search_mock, "总局公告"),
    ]
    llm = _FakeLLM(AIMessage(content="我直接答", tool_calls=[]))
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.POLICY_QUERY.value,
                "display_msg": "差旅住宿补贴怎么报？",
                "messages": [HumanMessage(content="差旅住宿补贴怎么报？")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert llm.calls == 2
    assert final.get("soft_reminded") is True
    assert not (final.get("tool_result") or "").strip()
    query_mock.assert_not_awaited()
    search_mock.assert_not_awaited()
    remind = [
        m for m in (final.get("messages") or []) if isinstance(m, SystemMessage)
    ]
    assert remind
    assert "search_official_data" in remind[-1].content


@pytest.mark.asyncio
async def test_graph_soft_remind_then_tool_on_second_turn():
    """软提醒后模型补调官方检索。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内"),
        _search_tool(search_mock, "总局公告"),
    ]
    llm = _SequencedLLM(
        [
            AIMessage(content="", tool_calls=[]),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "s1",
                        "name": TOOL_SEARCH_OFFICIAL,
                        "args": {
                            "query": "财政收支",
                            "region": "广东",
                            "period": "2026年一季度",
                            "topic": "fiscal",
                        },
                    }
                ],
            ),
        ]
    )
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": "2026广东省一季度财政",
                "messages": [HumanMessage(content="2026广东省一季度财政")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert llm.calls == 2
    assert "总局公告" in (final.get("tool_result") or "")
    search_mock.assert_awaited()
    query_mock.assert_not_awaited()


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


def test_after_agent_routes_pending_and_retry():
    assert after_agent({"pending_calls": [{"name": "x"}]}) == "tools"
    assert after_agent({"pending_calls": [], "retry_agent": True}) == "agent"
    assert after_agent({"pending_calls": [], "retry_agent": False}) == "finalize"


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
