"""附件硬路由子图：分类结果进节点，不把识别绑成模型 Tool。"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.observe import record

logger = logging.getLogger(__name__)

# 本请求的分类函数与文件元数据，避免把 bytes / db 写入图状态
upload_runtime: ContextVar[dict[str, Any]] = ContextVar("upload_agent_runtime")


class UploadState(TypedDict, total=False):
    """附件分类路由状态。识别/审查仍在图外流式执行。"""

    file_kind: str
    error: str
    user_message: str


def _runtime() -> dict[str, Any]:
    """读取本请求注入的分类器。"""
    return upload_runtime.get()


async def classify_file_node(state: UploadState) -> dict:
    """视觉分类：invoice / contract / chat；失败记 error。"""
    rt = _runtime()
    classify = rt["classify"]
    user_message = state.get("user_message") or rt.get("user_message") or ""
    try:
        kind = await classify(
            rt["file_bytes"],
            content_type=rt.get("content_type"),
            filename=rt.get("filename"),
            user_message=user_message,
            db=rt.get("db"),
            tenant_id=rt.get("tenant_id"),
        )
    except Exception as exc:
        logger.exception("upload classify failed")
        name = type(exc).__name__
        message = str(exc)
        if name == "DocumentUnreadableError":
            return {"file_kind": "error", "error": message}
        return {"file_kind": "error", "error": f"无法判断文件类型：{exc}"}
    if kind not in ("invoice", "contract", "chat"):
        kind = "chat"
    record("classify_file", file_kind=kind, tenant_id=str(rt.get("tenant_id") or ""))
    return {"file_kind": kind, "error": ""}


def after_classify(state: UploadState) -> str:
    """按分类硬路由，不交给模型选节点。"""
    kind = state.get("file_kind") or "chat"
    if kind == "error":
        return "error"
    if kind == "invoice":
        return "invoice"
    if kind == "contract":
        return "contract"
    return "file_chat"


async def invoice_node(state: UploadState) -> dict:
    """发票识别节点占位；实际 SSE 在编排器调用现有识别函数。"""
    return {"file_kind": "invoice"}


async def contract_node(state: UploadState) -> dict:
    """合同审查节点占位。"""
    return {"file_kind": "contract"}


async def file_chat_node(state: UploadState) -> dict:
    """非单据附件走普通文件对话。"""
    return {"file_kind": "chat"}


async def error_node(state: UploadState) -> dict:
    """分类失败，保留 error 文案。"""
    return {"file_kind": "error", "error": state.get("error") or "文件分类失败"}


def build_upload_graph():
    """无 checkpointer：只做分类路由。"""
    graph = StateGraph(UploadState)
    graph.add_node("classify_file", classify_file_node)
    graph.add_node("invoice", invoice_node)
    graph.add_node("contract", contract_node)
    graph.add_node("file_chat", file_chat_node)
    graph.add_node("error", error_node)
    graph.add_edge(START, "classify_file")
    graph.add_conditional_edges(
        "classify_file",
        after_classify,
        {
            "invoice": "invoice",
            "contract": "contract",
            "file_chat": "file_chat",
            "error": "error",
        },
    )
    graph.add_edge("invoice", END)
    graph.add_edge("contract", END)
    graph.add_edge("file_chat", END)
    graph.add_edge("error", END)
    return graph.compile()


_UPLOAD_GRAPH = None


def get_upload_graph():
    """懒编译附件子图。"""
    global _UPLOAD_GRAPH
    if _UPLOAD_GRAPH is None:
        _UPLOAD_GRAPH = build_upload_graph()
    return _UPLOAD_GRAPH
