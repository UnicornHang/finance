"""公开网页检索：给 Chat 提供最新财税政策证据，不替代企业知识库。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal, Never

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SearchProvider = Literal["bocha", "tavily"]

_BOCHA_DEFAULT_URL = "https://api.bochaai.com/v1/web-search"
_TAVILY_DEFAULT_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebSearchRuntime:
    """一次检索调用的有效配置（DB 覆盖 env 之后）。"""

    enabled: bool
    provider: SearchProvider
    api_key: str
    base_url: str
    timeout: int
    max_results: int
    fetch_pages: int
    fetch_max_chars: int

    @classmethod
    def from_settings(cls) -> "WebSearchRuntime":
        """环境变量兜底。"""
        provider: SearchProvider = settings.web_search_provider
        return cls(
            enabled=bool(settings.web_search_enabled),
            provider=provider,
            api_key=(settings.web_search_api_key or "").strip(),
            base_url=(settings.web_search_base_url or "").strip(),
            timeout=int(settings.web_search_timeout or 15),
            max_results=int(settings.web_search_max_results or 16),
            fetch_pages=int(settings.web_search_fetch_pages or 0),
            fetch_max_chars=int(settings.web_search_fetch_max_chars or 4000),
        )

    def endpoint(self) -> str:
        """解析实际请求地址。"""
        if self.base_url.startswith("http://") or self.base_url.startswith("https://"):
            return self.base_url
        if self.provider == "bocha":
            return _BOCHA_DEFAULT_URL
        if self.provider == "tavily":
            return _TAVILY_DEFAULT_URL
        unreachable: Never = self.provider
        raise ValueError(f"未知检索提供商: {unreachable}")


class WebSearchService:
    """可插拔公开检索。无密钥时明确失败，禁止调用方让模型编造。"""

    def is_configured(self, runtime: WebSearchRuntime | None = None) -> bool:
        """是否已打开且具备调用条件。"""
        rt = runtime or WebSearchRuntime.from_settings()
        return bool(rt.enabled and rt.api_key)

    async def search(
        self,
        query: str,
        *,
        runtime: WebSearchRuntime | None = None,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """检索公开网页。

        include_domains：优先限制站点（Tavily 原生；博查写入查询词）。
        """
        rt = runtime or WebSearchRuntime.from_settings()
        q = (query or "").strip()
        if not q:
            return {"ok": False, "provider": rt.provider, "query": q, "hits": [], "error": "检索词为空"}
        if not rt.enabled:
            return {
                "ok": False,
                "provider": rt.provider,
                "query": q,
                "hits": [],
                "error": "公开检索未启用（请在管理端「工具配置」打开）",
            }
        if not rt.api_key:
            return {
                "ok": False,
                "provider": rt.provider,
                "query": q,
                "hits": [],
                "error": "未配置检索 API Key",
            }

        provider: SearchProvider = rt.provider
        limit = max_results or rt.max_results or 16
        domains = include_domains or []
        try:
            if provider == "bocha":
                hits = await self._search_bocha(rt, q, limit, domains)
            elif provider == "tavily":
                hits = await self._search_tavily(rt, q, limit, domains)
            else:
                unreachable: Never = provider
                raise ValueError(f"未知检索提供商: {unreachable}")
        except Exception as exc:
            logger.exception("web search failed provider=%s query=%s", provider, q[:80])
            return {
                "ok": False,
                "provider": provider,
                "query": q,
                "hits": [],
                "error": f"检索失败：{exc}",
            }

        return {"ok": True, "provider": provider, "query": q, "hits": hits, "error": None}

    async def test_connectivity(self, runtime: WebSearchRuntime) -> dict[str, Any]:
        """用一条轻量查询验证 Key 是否可用。"""
        if not runtime.api_key:
            return {"ok": False, "message": "未配置 API Key", "latency_ms": 0}
        started = time.perf_counter()
        result = await self.search(
            "增值税 site:chinatax.gov.cn",
            runtime=runtime,
            max_results=1,
            include_domains=["chinatax.gov.cn"],
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if result.get("ok"):
            n = len(result.get("hits") or [])
            return {
                "ok": True,
                "message": f"检索成功，返回 {n} 条结果",
                "latency_ms": elapsed_ms,
            }
        return {
            "ok": False,
            "message": str(result.get("error") or "检索失败"),
            "latency_ms": elapsed_ms,
        }

    async def _search_bocha(
        self,
        runtime: WebSearchRuntime,
        query: str,
        limit: int,
        include_domains: list[str],
    ) -> list[dict[str, str]]:
        """调用博查 Web Search。站点限制写入查询词。"""
        url = runtime.endpoint()
        q = query
        if include_domains and "site:" not in q.lower():
            site_or = " OR ".join(f"site:{d}" for d in include_domains)
            q = f"{query} ({site_or})"
        payload = {
            "query": q,
            "count": limit,
            # 官方统计稿常跨年发布；限制 oneYear 会漏掉已公布的财政数据
            "freshness": "noLimit",
            "summary": True,
        }
        headers = {
            "Authorization": f"Bearer {runtime.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        pages = (
            ((data or {}).get("data") or {}).get("webPages") or {}
        ).get("value") or []
        hits: list[dict[str, str]] = []
        for item in pages[:limit]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("name") or item.get("title") or "").strip()
            link = str(item.get("url") or "").strip()
            snippet = str(
                item.get("summary") or item.get("snippet") or item.get("description") or ""
            ).strip()
            published = str(
                item.get("dateLastCrawled") or item.get("datePublished") or ""
            ).strip()
            if not title and not link:
                continue
            hits.append(
                {
                    "title": title or link,
                    "url": link,
                    "snippet": snippet[:800],
                    "published_at": published,
                }
            )
        return hits

    async def _search_tavily(
        self,
        runtime: WebSearchRuntime,
        query: str,
        limit: int,
        include_domains: list[str],
    ) -> list[dict[str, str]]:
        """调用 Tavily Search。正文靠后续官方页抓取，此处用 basic 省额度。"""
        url = runtime.endpoint()
        payload: dict[str, Any] = {
            "api_key": runtime.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": limit,
            "include_answer": False,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        results = (data or {}).get("results") or []
        hits: list[dict[str, str]] = []
        for item in results[:limit]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            link = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or "").strip()
            published = str(item.get("published_date") or "").strip()
            if not title and not link:
                continue
            hits.append(
                {
                    "title": title or link,
                    "url": link,
                    "snippet": snippet[:800],
                    "published_at": published,
                }
            )
        return hits


web_search_service = WebSearchService()
