"""只读工具：空库门槛与检索格式化。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.policy import TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL
from app.agent.tools.catalog import build_text_tools, persistable_tool_calls, pick_tools


def _tool(tools, name):
    return next(t for t in tools if t.name == name)


@pytest.mark.asyncio
async def test_query_policy_high_score():
    """高相关分返回标题与正文。"""
    hits = [
        {
            "title": "差旅补贴管理办法",
            "doc_type": "policy",
            "score": 0.9,
            "content": "住宿上限 500",
        }
    ]
    trace: dict = {}
    with patch("app.agent.tools.catalog.rag_service") as mock_rag:
        mock_rag.retrieve = AsyncMock(return_value=hits)
        tools = build_text_tools(MagicMock(), "tenant", trace)
        text = await _tool(tools, TOOL_QUERY_POLICY).ainvoke({"question": "差旅"})
    assert "【制度1】" in text
    assert "差旅补贴管理办法" in text
    assert "住宿上限 500" in text
    assert trace["policy"]["tool"] == TOOL_QUERY_POLICY
    assert trace["policy"]["hit_count"] == 1
    assert trace["policy"]["usable"] is True


@pytest.mark.asyncio
async def test_query_policy_low_score_is_empty():
    """低分视为未命中，禁止外网口径。"""
    hits = [{"title": "无关", "doc_type": "policy", "score": 0.1, "content": "chinatax"}]
    trace: dict = {}
    with patch("app.agent.tools.catalog.rag_service") as mock_rag:
        mock_rag.retrieve = AsyncMock(return_value=hits)
        tools = build_text_tools(MagicMock(), "tenant", trace)
        text = await _tool(tools, TOOL_QUERY_POLICY).ainvoke({"question": "差旅"})
    assert "知识库暂无" in text
    assert "chinatax.gov.cn" not in text
    assert trace["policy"]["tool"] == TOOL_QUERY_POLICY
    assert trace["policy"]["usable"] is False


@pytest.mark.asyncio
async def test_search_official_data_formats_and_traces():
    """搜索成功写入 trace，并带上标题与链接。"""
    payload = {
        "ok": True,
        "provider": "bocha",
        "query": "增值税",
        "hits": [
            {
                "title": "总局公告",
                "url": "https://www.chinatax.gov.cn/a",
                "snippet": "优惠",
                "source_kind": "official",
            }
        ],
        "pages": [],
        "error": None,
    }
    trace: dict = {}
    with patch("app.agent.tools.catalog.tool_config_service") as mock_cfg:
        mock_cfg.resolve_web_search = AsyncMock(side_effect=RuntimeError("no cfg"))
        with patch("app.agent.tools.catalog.official_policy_service") as mock_pol:
            mock_pol.search_and_fetch = AsyncMock(return_value=payload)
            tools = build_text_tools(MagicMock(), "tenant", trace)
            text = await _tool(tools, TOOL_SEARCH_OFFICIAL).ainvoke(
                {
                    "query": "增值税",
                    "region": "广东",
                    "period": "2026",
                    "topic": "tax",
                }
            )
    assert "总局公告" in text
    assert "https://www.chinatax.gov.cn/a" in text
    assert TOOL_SEARCH_OFFICIAL == "search_official_data"
    assert trace["search"]["tool"] == TOOL_SEARCH_OFFICIAL
    assert trace["search"]["ok"] is True
    assert trace["search"]["region"] == "广东"
    assert trace["search"]["sources"][0]["index"] == 1
    assert trace["search"]["sources"][0]["url"] == "https://www.chinatax.gov.cn/a"
    mock_pol.search_and_fetch.assert_awaited()
    kwargs = mock_pol.search_and_fetch.await_args.kwargs
    assert kwargs.get("region") == "广东"
    assert kwargs.get("period") == "2026"
    assert kwargs.get("topic") == "tax"


def test_pick_tools_filters_allowlist():
    tools = build_text_tools(MagicMock(), "tenant", {})
    picked = pick_tools(tools, [TOOL_QUERY_POLICY])
    assert [t.name for t in picked] == [TOOL_QUERY_POLICY]


def test_persistable_tool_calls_prefers_policy():
    """制度痕迹写入 tool=query_policy，公开检索挂在 search 下。"""
    merged = persistable_tool_calls(
        {
            "policy": {"tool": TOOL_QUERY_POLICY, "hit_count": 2},
            "search": {"tool": TOOL_SEARCH_OFFICIAL, "ok": True},
        }
    )
    assert merged["tool"] == TOOL_QUERY_POLICY
    assert merged["search"]["ok"] is True
    assert persistable_tool_calls({}) is None
