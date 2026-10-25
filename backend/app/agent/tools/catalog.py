"""B1 只读工具：企业制度 RAG、权威站检索。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.policy import POLICY_RAG_MIN_SCORE, TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL
from app.services.official_policy_service import (
    format_official_policy_context,
    official_policy_service,
    sources_from_hits,
)
from app.services.rag_service import rag_service
from app.services.tool_config_service import tool_config_service
from app.services.web_search_service import WebSearchRuntime

logger = logging.getLogger(__name__)


def policy_sources_from_hits(hits: list[dict]) -> list[dict[str, Any]]:
    """将制度命中序列化为可落库 / SSE 的 sources（index 从 1，kind=policy）。"""
    out: list[dict[str, Any]] = []
    for i, h in enumerate(hits[:5], start=1):
        title = str(h.get("title") or "未命名文档")
        doc_id = str(h.get("doc_id") or "")
        chunk_id = str(h.get("chunk_id") or "")
        section = str(h.get("section_path") or "").strip()
        body = (h.get("content") or "").strip()
        snippet = body[:300] if body else section
        # 前端可识别的伪 URL；真正打开走知识库管理，不走外链
        url = f"kb://doc/{doc_id}" if doc_id else f"kb://chunk/{chunk_id or i}"
        out.append(
            {
                "index": i,
                "title": title,
                "url": url,
                "snippet": snippet,
                "source_kind": "policy",
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "section_path": section,
                "favicon_host": "",
            }
        )
    return out


def policy_retrieve_trace(question: str, hits: list[dict]) -> dict[str, Any]:
    """制度检索落库痕迹，供数据概览「本月检索」统计。"""
    best = float(hits[0]["score"]) if hits else 0.0
    usable = bool(hits) and best >= POLICY_RAG_MIN_SCORE
    sources = policy_sources_from_hits(hits) if usable else []
    return {
        "tool": TOOL_QUERY_POLICY,
        "query": (question or "")[:200],
        "hit_count": len(hits),
        "best_score": round(best, 3),
        "usable": usable,
        "sources": sources,
    }


def persistable_tool_calls(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    """合并本轮制度检索 / 公开检索痕迹，写入 messages.tool_calls。"""
    if not trace:
        return None
    policy = trace.get("policy")
    search = trace.get("search")
    if not policy and not search:
        return None
    if policy and search:
        return {**policy, "search": search}
    return policy or search


def build_text_tools(
    db: AsyncSession,
    tenant_id: str,
    trace: dict[str, Any],
) -> list[StructuredTool]:
    """构造本请求可用的 StructuredTool；trace 用于回写检索元数据。"""

    async def query_policy(question: str) -> str:
        """查询本公司内部制度、差旅报销、补贴标准等企业知识库。不用于国家税法或官网检索。"""
        try:
            hits = await rag_service.retrieve(
                db, question, tenant_id, top_k=5, doc_type=None
            )
        except Exception:
            logger.exception("query_policy retrieve failed")
            hits = []
        trace["policy"] = policy_retrieve_trace(question, hits)
        best = float(hits[0]["score"]) if hits else 0.0
        if not hits or best < POLICY_RAG_MIN_SCORE:
            return "知识库暂无相关规定。请明确告知用户，不要用外网或国家机关标准冒充本公司制度。"
        parts: list[str] = []
        for i, h in enumerate(hits[:5], start=1):
            title = h.get("title") or "未命名文档"
            doc_type = h.get("doc_type") or ""
            score = h.get("score")
            score_s = f"{float(score):.3f}" if score is not None else "-"
            doc_id = h.get("doc_id") or ""
            chunk_id = h.get("chunk_id") or ""
            section = (h.get("section_path") or "").strip()
            meta = f"类型:{doc_type}，相关度:{score_s}"
            if section:
                meta += f"，章节:{section}"
            if doc_id:
                meta += f"，doc_id:{doc_id}"
            if chunk_id:
                meta += f"，chunk_id:{chunk_id}"
            body = (h.get("content") or "").strip()
            parts.append(f"【制度{i}】 《{title}》（{meta}）\n{body}")
        return "\n\n".join(parts)

    async def search_official_data(
        query: str,
        region: str | None = None,
        period: str | None = None,
        topic: str | None = None,
    ) -> str:
        """检索公开网页上的财税政策与财政数据（全网检索，官方来源优先展示）。

        结合整段对话理解本轮问题后再填参数。query 只写一句问话，保留对话中的年份和地区，
        不要并列堆砌多个主题，不要改年份。指代按对话补全，并尽量填写 region / period / topic。
        换了地区或改问全国时以本轮为准。部门预决算不是全区、全省总收入。
        回答时请用 [n] 引用返回条目。
        不用于本公司差旅报销制度，也不可假装完成发票查验或工商查询。
        """
        try:
            runtime = await tool_config_service.resolve_web_search(db, tenant_id)
        except Exception:
            logger.exception("resolve web search config failed, fall back to env")
            runtime = WebSearchRuntime.from_settings()
        search_result = await official_policy_service.search_and_fetch(
            query,
            runtime=runtime,
            region=region,
            period=period,
            topic=topic,
        )
        hits = search_result.get("hits") or []
        sources = search_result.get("sources") or sources_from_hits(hits)
        trace["search"] = {
            "tool": TOOL_SEARCH_OFFICIAL,
            "question": query,
            "query": search_result.get("query"),
            "region": region,
            "period": period,
            "topic": topic,
            "provider": search_result.get("provider"),
            "ok": search_result.get("ok"),
            "hit_count": len(hits),
            "fetched_count": len(search_result.get("pages") or []),
            "error": search_result.get("error"),
            "sources": sources,
        }
        return format_official_policy_context(search_result)

    return [
        StructuredTool.from_function(
            coroutine=query_policy,
            name=TOOL_QUERY_POLICY,
            description=query_policy.__doc__ or TOOL_QUERY_POLICY,
        ),
        StructuredTool.from_function(
            coroutine=search_official_data,
            name=TOOL_SEARCH_OFFICIAL,
            description=search_official_data.__doc__ or TOOL_SEARCH_OFFICIAL,
        ),
    ]


def pick_tools(all_tools: list[StructuredTool], allowed: list[str]) -> list[StructuredTool]:
    """按白名单裁剪工具。"""
    allow = set(allowed)
    return [t for t in all_tools if t.name in allow]
