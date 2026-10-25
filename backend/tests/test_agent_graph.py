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
    """制度意图漏调且语义无法解析时，强制知识库，不串外网。"""
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
    assert llm.calls == 2
    assert "《差旅》住宿 500" in (final.get("tool_result") or "")
    query_mock.assert_awaited_once_with(question)
    search_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_chitchat_does_not_force_tool():
    """闲聊允许调工具，但不强制补调。"""
    query_mock = AsyncMock()
    search_mock = AsyncMock()
    bound = [
        _query_tool(query_mock, "库内"),
        _search_tool(search_mock, "外网"),
    ]
    llm = _FakeLLM(AIMessage(content="你好呀", tool_calls=[]))
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        final = await get_text_graph().ainvoke(
            {
                "intent": Intent.CHITCHAT.value,
                "display_msg": "你好",
                "messages": [HumanMessage(content="你好")],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert llm.calls == 1
    assert (final.get("tool_result") or "") == ""
    query_mock.assert_not_awaited()
    search_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_forces_official_search_for_followup():
    """语义结果无法解析时，用本轮原话检索，不把上一轮地区写进去。"""
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
    assert llm.calls == 2
    assert "总局公告" in (final.get("tool_result") or "")
    search_mock.assert_awaited_once_with(
        question, region=None, period=None, topic=None
    )
    query_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_keeps_model_resolution_of_deixis():
    """模型把「那边」判成海南时，代码不改写它的检索参数。"""
    search_mock = AsyncMock()
    bound = [_search_tool(search_mock, "海南税收")]
    question = "那边的企业税收是怎样的？"
    llm = _FakeLLM(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "s1",
                    "name": TOOL_SEARCH_OFFICIAL,
                    "args": {
                        "query": "2026年海南省企业税收政策",
                        "region": "海南省",
                        "period": "2026年",
                        "topic": "企业税收",
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
                "messages": [
                    HumanMessage(content="2026年海南省的收入怎样"),
                    AIMessage(content="上半年地方一般公共预算收入510.5亿元"),
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
    search_mock.assert_awaited_once_with(
        "2026年海南省企业税收政策",
        region="海南省",
        period="2026年",
        topic="企业税收",
    )


@pytest.mark.asyncio
async def test_graph_semantic_json_fills_skipped_tool():
    """模型没调工具时，采用它随后给出的 JSON 参数，而不是词表改写。"""
    search_mock = AsyncMock()
    bound = [_search_tool(search_mock, "海南税收")]
    question = "那边的企业税收是怎样的？"
    llm = _SequencedLLM(
        [
            AIMessage(content="我先不搜", tool_calls=[]),
            AIMessage(
                content=(
                    '{"query":"2026年海南省企业税收政策","region":"海南省",'
                    '"period":null,"topic":"企业税收"}'
                ),
                tool_calls=[],
            ),
        ]
    )
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": question,
                "messages": [
                    HumanMessage(content="2026年海南省的收入怎样"),
                    AIMessage(content="上半年收入510.5亿元"),
                    HumanMessage(content=question),
                ],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    assert llm.calls == 2
    search_mock.assert_awaited_once_with(
        "2026年海南省企业税收政策",
        region="海南省",
        period=None,
        topic="企业税收",
    )


@pytest.mark.asyncio
async def test_graph_national_followup_does_not_inherit_province():
    """语义结果无法解析时，不靠词表把上一轮的省写进检索。"""
    search_mock = AsyncMock()
    bound = [_search_tool(search_mock, "全国政策")]
    question = "全国小微企业政策呢？"
    llm = _FakeLLM(AIMessage(content="无法解析", tool_calls=[]))
    token = graph_runtime.set({"llm": llm, "bound_tools": bound})
    try:
        await get_text_graph().ainvoke(
            {
                "intent": Intent.PUBLIC_TAX.value,
                "display_msg": question,
                "messages": [
                    HumanMessage(content="2026年海南省的收入怎样"),
                    HumanMessage(content=question),
                ],
                "tool_round": 0,
                "pending_calls": [],
                "tool_result": "",
            }
        )
    finally:
        graph_runtime.reset(token)
    search_mock.assert_awaited_once_with(
        question, region=None, period=None, topic=None
    )


@pytest.mark.asyncio
async def test_graph_keeps_model_tool_args_verbatim():
    """模型已给出参数时原样执行，代码不按字面槽位改写。"""
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
        "广东省2026年一季度财政收支",
        region="广东省",
        period="2026年一季度",
        topic="财政收支",
    )
    query_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_keeps_slots_that_appear_in_current_question():
    """模型填写的检索词和槽位原样传给检索。"""
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
        "全国财政收支",
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
