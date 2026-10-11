"""无附件文本：LangGraph 状态图（分类结果由调用方注入）。"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from app.agent.llm_adapter import ChatFinanceLLM
from app.agent.observe import record
from app.agent.policy import (
    MAX_TOOL_ROUNDS,
    TOOL_QUERY_POLICY,
    TOOL_SEARCH_OFFICIAL,
    required_tool_for_intent,
    tools_for_intent,
)
from app.agent.router import Intent

logger = logging.getLogger(__name__)

# 本请求的 llm / tools，避免依赖 LangGraph 是否把 config 传进节点
graph_runtime: ContextVar[dict[str, Any]] = ContextVar("text_agent_runtime")


class AgentState(TypedDict, total=False):
    """单次请求图状态，不含 db。"""

    intent: str
    display_msg: str
    allowed_tools: list[str]
    tool_round: int
    pending_calls: list[dict]
    tool_result: str
    messages: list[BaseMessage]


def _runtime() -> dict[str, Any]:
    """读取本请求注入的运行时。"""
    return graph_runtime.get()


def _intent(state: AgentState) -> Intent:
    """把 state 里的字符串还原为 Intent。"""
    try:
        return Intent(state.get("intent") or Intent.CHITCHAT.value)
    except ValueError:
        return Intent.CHITCHAT


def _arg_for_tool(name: str, display_msg: str, args: dict | None) -> dict:
    """无参时把用户原话填进工具的字符串字段。"""
    if args:
        return args
    if name == TOOL_QUERY_POLICY:
        return {"question": display_msg}
    if name == TOOL_SEARCH_OFFICIAL:
        return {"query": display_msg}
    return {"query": display_msg}


async def gate_node(state: AgentState) -> dict:
    """写入白名单。"""
    allowed = tools_for_intent(_intent(state))
    return {
        "allowed_tools": allowed,
        "tool_round": int(state.get("tool_round") or 0),
        "pending_calls": [],
        "tool_result": state.get("tool_result") or "",
    }


def after_gate(state: AgentState) -> str:
    """无工具意图跳过 agent。"""
    if state.get("allowed_tools"):
        return "agent"
    return "finalize"


def _slot_in_question(value: object, question: str) -> bool:
    """槽位必须是本轮原话的连续子串，避免带上上一轮的地区或期间。"""
    if not isinstance(value, str):
        return False
    token = value.strip()
    return bool(token) and token in question


def _anchor_call(name: str, question: str, call: dict) -> dict:
    """必调工具的主查询改成本轮用户原话，并丢掉不属于本轮的槽位。"""
    args = dict(call.get("args") or {})
    if name == TOOL_QUERY_POLICY:
        args["question"] = question or str(args.get("question") or "")
    elif name == TOOL_SEARCH_OFFICIAL:
        args["query"] = question or str(args.get("query") or "")
        for key in ("region", "period", "topic"):
            if not _slot_in_question(args.get(key), question):
                args.pop(key, None)
    return {
        "id": str(call.get("id") or uuid4()),
        "name": name,
        "args": args,
    }


def _anchor_required_calls(
    intent: Intent,
    allowed: list[str],
    question: str,
    legal: list[dict],
) -> list[dict]:
    """保证必调工具执行一次。模型已调用时仍把查询词锚定到本轮原话。"""
    required = required_tool_for_intent(intent)
    if not required or required not in allowed:
        return legal
    anchored: list[dict] = []
    found = False
    for call in legal:
        if call.get("name") != required:
            anchored.append(call)
            continue
        if found:
            continue
        found = True
        anchored.append(_anchor_call(required, question, call))
    if found:
        return anchored
    record("force_tool", tool=required, intent=intent.value)
    anchored.insert(0, _anchor_call(required, question, {"name": required, "args": {}}))
    return anchored


async def agent_node(state: AgentState) -> dict:
    """绑白名单工具调用模型；必调工具漏调时用本轮原话补上，不再放行空检索。"""
    rt = _runtime()
    llm: ChatFinanceLLM = rt["llm"]
    tools: list[BaseTool] = rt.get("bound_tools") or []
    messages: list[BaseMessage] = list(state.get("messages") or [])
    allowed = list(state.get("allowed_tools") or [])
    round_n = int(state.get("tool_round") or 0)
    display_msg = state.get("display_msg") or ""
    already = (state.get("tool_result") or "").strip()

    bind = [t for t in tools if t.name in set(allowed)] if allowed and not already else []
    ai: AIMessage = await llm.ainvoke(messages, tools=bind or None)

    legal: list[dict] = []
    for tc in ai.tool_calls or []:
        name = tc.get("name")
        if name in allowed:
            legal.append(
                {
                    "id": tc.get("id") or str(uuid4()),
                    "name": name,
                    "args": tc.get("args") or {},
                }
            )
        else:
            logger.warning("drop illegal tool call name=%s allowed=%s", name, allowed)

    if legal and round_n >= MAX_TOOL_ROUNDS:
        logger.info("max tool rounds reached, ignore further calls")
        legal = []
    elif round_n < MAX_TOOL_ROUNDS and not already:
        legal = _anchor_required_calls(_intent(state), allowed, display_msg, legal)

    return {
        "messages": messages + [ai],
        "pending_calls": legal,
        "tool_round": round_n + (1 if legal else 0),
    }


async def tools_node(state: AgentState) -> dict:
    """执行白名单内的 pending_calls，非法名跳过。"""
    rt = _runtime()
    tools: list[BaseTool] = rt.get("bound_tools") or []
    by_name = {t.name: t for t in tools}
    allowed = set(state.get("allowed_tools") or [])
    display_msg = state.get("display_msg") or ""
    messages = list(state.get("messages") or [])
    chunks: list[str] = []
    if state.get("tool_result"):
        chunks.append(state["tool_result"])

    for call in state.get("pending_calls") or []:
        name = call.get("name")
        if name not in allowed:
            logger.warning("skip tool not in allowlist: %s", name)
            continue
        tool = by_name.get(name)
        if tool is None:
            logger.warning("skip unknown tool: %s", name)
            continue
        args = _arg_for_tool(name, display_msg, call.get("args"))
        try:
            result = await tool.ainvoke(args)
        except Exception as exc:
            logger.exception("tool %s failed", name)
            result = f"工具 {name} 调用失败：{exc}"
        text = result if isinstance(result, str) else str(result)
        chunks.append(text)
        record("tool", tool=str(name), intent=str(state.get("intent") or ""))
        messages.append(
            ToolMessage(
                content=text,
                tool_call_id=str(call.get("id") or name),
                name=name,
            )
        )

    return {
        "messages": messages,
        "tool_result": "\n\n".join(c for c in chunks if c).strip(),
        "pending_calls": [],
    }


def after_agent(state: AgentState) -> str:
    """有待执行工具进 tools，否则结束。"""
    if state.get("pending_calls"):
        return "tools"
    return "finalize"


async def finalize_node(state: AgentState) -> dict:
    """占位结束节点。"""
    return {}


def build_text_graph():
    """编译无 checkpointer 的文本图。"""
    graph = StateGraph(AgentState)
    graph.add_node("gate", gate_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "gate")
    graph.add_conditional_edges(
        "gate",
        after_gate,
        {"agent": "agent", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "agent",
        after_agent,
        {"tools": "tools", "finalize": "finalize"},
    )
    graph.add_edge("tools", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


_TEXT_GRAPH = None


def get_text_graph():
    """懒编译进程内单图结构；运行时状态仍按次传入。"""
    global _TEXT_GRAPH
    if _TEXT_GRAPH is None:
        _TEXT_GRAPH = build_text_graph()
    return _TEXT_GRAPH
