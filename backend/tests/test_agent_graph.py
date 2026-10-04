"""LangGraph 文本图：白名单、强制补调、拒绝非法工具。"""

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
    def __init__(self, message: AIMessage):
        self.message = message
        self.calls = 0

    async def ainvoke(self, messages, *, tools=None, temperature=None):
        self.calls += 1
        return self.message


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

    async def search_official_policy(query: str) -> str:
        await mock(query)
        return result

    return StructuredTool.from_function(
        coroutine=search_official_policy,
        name=TOOL_SEARCH_OFFICIAL,
        description="检索公开财税",
    )


@pytest.mark.asyncio
async def test_graph_policy_forces_query_tool():
    """制度意图无 tool_calls 时强制 query_policy。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "《差旅》住宿 500"),
        _search_tool(search_mock, "SHOULD_NOT"),
    ]
    llm = _FakeLLM(AIMessage(content="", tool_calls=[]))
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
    assert "差旅" in (final.get("tool_result") or "")
    query_mock.assert_awaited()
    search_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_public_tax_forces_search_tool():
    """公开财税意图强制 search_official_policy，不碰知识库。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内"),
        _search_tool(search_mock, "总局公告"),
    ]
    llm = _FakeLLM(AIMessage(content="", tool_calls=[]))
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": "广州企业所得税优惠",
                "messages": [HumanMessage(content="广州企业所得税优惠")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert "总局公告" in (final.get("tool_result") or "")
    search_mock.assert_awaited()
    query_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_drops_illegal_search_on_policy():
    """制度意图下搜索 call 被丢弃，改强制知识库工具。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内制度"),
        _search_tool(search_mock, "外网"),
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
                "display_msg": "差旅怎么报",
                "messages": [HumanMessage(content="差旅怎么报")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    search_mock.assert_not_awaited()
    query_mock.assert_awaited()
    assert "库内制度" in (final.get("tool_result") or "")


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
