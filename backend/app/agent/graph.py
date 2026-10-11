"""无附件文本：LangGraph 状态图（分类结果由调用方注入）。"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from typing import Any, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from app.agent.llm_adapter import ChatFinanceLLM
from app.agent.observe import record
from app.agent.policy import (
    MAX_TOOL_ROUNDS,
    TOOL_QUERY_POLICY,
    TOOL_SEARCH_OFFICIAL,
    needs_retrieval,
    tools_for_intent,
)
from app.agent.router import Intent

logger = logging.getLogger(__name__)

_RESOLVE_ARGS_TEXT = (
    "你刚才没有调用工具。请阅读上面的整段对话和上一轮话题，"
    "判断本轮该查公开数据还是本公司制度，只输出一个 JSON 对象，不要解释。\n"
    "用户本轮原话：{question}\n"
    '工具名 tool 只能是 "search_official_data" 或 "query_policy"。\n'
    "公开的收入、财政、税收、政策用 search_official_data，字段为 query、region、period、topic。\n"
    "只有用户明确在问本公司制度、差旅报销、内部补贴时才用 query_policy，字段为 question。\n"
    "query 只写一句问话，保留对话里的年份和地区，不要并列堆砌主题，不要改年份。"
    "没有把握的字段填 null。用户换了话题或地区时以本轮语义为准。"
    "追问政策就检索政策，不要改回上一轮的收入问题，也不要把公开问题改写成公司制度。"
)
_RETRIEVAL_TOOLS = frozenset({TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL})

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
    """主查询字段为空时才回填用户原话，其余参数保持模型给出的值。"""
    data = dict(args or {})
    if name == TOOL_QUERY_POLICY:
        if not str(data.get("question") or "").strip():
            data["question"] = display_msg
        return data
    if not str(data.get("query") or "").strip():
        data["query"] = display_msg
    return data


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


def _parse_json_object(text: str) -> dict | None:
    """从模型输出中抽出 JSON 对象。解析失败则交给调用方兜底。"""
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _text_slot(value: object) -> str | None:
    """保留模型给出的非空字符串；null 和空白视为未判断。"""
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or token.lower() == "null":
        return None
    return token


def _call_from_resolution(payload: dict, allowed: set[str]) -> dict | None:
    """把模型的 JSON 判断转成一次工具调用，不改写字段内容。"""
    name = _text_slot(payload.get("tool")) or ""
    if name not in allowed:
        if _text_slot(payload.get("query")) and TOOL_SEARCH_OFFICIAL in allowed:
            name = TOOL_SEARCH_OFFICIAL
        elif _text_slot(payload.get("question")) and TOOL_QUERY_POLICY in allowed:
            name = TOOL_QUERY_POLICY
        else:
            return None
    if name == TOOL_QUERY_POLICY:
        question = _text_slot(payload.get("question")) or _text_slot(payload.get("query"))
        if not question:
            return None
        return {"id": str(uuid4()), "name": name, "args": {"question": question}}
    query = _text_slot(payload.get("query")) or _text_slot(payload.get("question"))
    if not query:
        return None
    args: dict[str, str] = {"query": query}
    for key in ("region", "period", "topic"):
        slot = _text_slot(payload.get(key))
        if slot:
            args[key] = slot
    return {"id": str(uuid4()), "name": name, "args": args}


async def _semantic_retrieval_call(
    llm: ChatFinanceLLM,
    messages: list[BaseMessage],
    question: str,
    allowed: set[str],
) -> dict | None:
    """两个检索工具都没调时，再请模型按对话选择工具和参数。"""
    ai = await llm.ainvoke(
        [
            *messages,
            HumanMessage(content=_RESOLVE_ARGS_TEXT.format(question=question)),
        ],
        tools=None,
    )
    content = ai.content if isinstance(ai.content, str) else str(ai.content or "")
    payload = _parse_json_object(content)
    if payload is None:
        return None
    return _call_from_resolution(payload, allowed)


def _fallback_retrieval_call(allowed: set[str], question: str) -> dict | None:
    """语义结果无法解析时，用本轮原话做公开检索。"""
    if TOOL_SEARCH_OFFICIAL in allowed:
        return {
            "id": str(uuid4()),
            "name": TOOL_SEARCH_OFFICIAL,
            "args": {"query": question},
        }
    if TOOL_QUERY_POLICY in allowed:
        return {
            "id": str(uuid4()),
            "name": TOOL_QUERY_POLICY,
            "args": {"question": question},
        }
    return None


async def _ensure_retrieval_call(
    llm: ChatFinanceLLM,
    intent: Intent,
    allowed: list[str],
    question: str,
    legal: list[dict],
    messages: list[BaseMessage],
) -> list[dict]:
    """模型已选检索工具时原样执行。都没选时再做一次语义判断。"""
    allow = set(allowed)
    if not needs_retrieval(intent) or not (allow & _RETRIEVAL_TOOLS):
        return legal
    if any(call.get("name") in _RETRIEVAL_TOOLS for call in legal):
        return legal
    resolved = await _semantic_retrieval_call(llm, messages, question, allow)
    if resolved is not None:
        record("semantic_tool_args", tool=str(resolved.get("name")), intent=intent.value)
        return [resolved, *legal]
    fallback = _fallback_retrieval_call(allow, question)
    if fallback is None:
        return legal
    record("force_tool", tool=str(fallback.get("name")), intent=intent.value)
    return [fallback, *legal]


async def agent_node(state: AgentState) -> dict:
    """绑白名单工具调用模型。模型给出的参数原样执行；漏调时再请它做语义解析。"""
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
        legal = await _ensure_retrieval_call(
            llm, _intent(state), allowed, display_msg, legal, messages
        )

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
