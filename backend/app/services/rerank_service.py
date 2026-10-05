"""交叉编码器 Rerank：通义原生 / 兼容协议 / Cohere / Jina。"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.services.rag_hybrid import normalize_rerank_scores

logger = logging.getLogger(__name__)

_DASHSCOPE_NATIVE = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)


class RerankService:
    """对融合后的候选做二次精排；失败时由调用方回退 RRF 顺序。"""

    def _api_key(self) -> str:
        return (
            settings.rerank_api_key
            or settings.embedding_api_key
            or settings.llm_contract_api_key
            or settings.llm_policy_api_key
            or settings.llm_chitchat_api_key
            or ""
        ).strip()

    def available(self) -> bool:
        """开关打开且能解析到密钥才真正调用。"""
        return bool(settings.rag_rerank_enabled and self._api_key())

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int,
    ) -> list[tuple[int, float]] | None:
        """返回 (原下标, 归一化相关分) 列表；失败返回 None。"""
        if not self.available() or not documents or not (query or "").strip():
            return None
        top_n = max(1, min(top_n, len(documents)))
        provider = (settings.rerank_provider or "dashscope").lower()
        try:
            raw = await self._invoke(provider, query, documents, top_n)
        except Exception:
            logger.exception("rerank request failed provider=%s", provider)
            return None
        parsed = self._parse_results(raw, n_docs=len(documents))
        if not parsed:
            logger.warning("rerank empty/invalid response provider=%s", provider)
            return None
        scores = [s for _, s in parsed]
        norm = normalize_rerank_scores(scores)
        return [(idx, norm[i]) for i, (idx, _) in enumerate(parsed)]

    async def _invoke(
        self,
        provider: str,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> dict[str, Any]:
        """按提供商发 HTTP。"""
        key = self._api_key()
        timeout = settings.rerank_timeout
        model = settings.rerank_model
        match provider:
            case "dashscope":
                return await self._dashscope(key, model, query, documents, top_n, timeout)
            case "cohere":
                return await self._cohere(key, model, query, documents, top_n, timeout)
            case "jina":
                return await self._jina(key, model, query, documents, top_n, timeout)
            case "openai_compatible":
                return await self._openai_compatible(
                    key, model, query, documents, top_n, timeout
                )
            case _:
                raise ValueError(f"unsupported rerank provider: {provider}")

    async def _dashscope(
        self,
        key: str,
        model: str,
        query: str,
        documents: list[str],
        top_n: int,
        timeout: int,
    ) -> dict[str, Any]:
        """通义文本排序原生接口。"""
        payload = {
            "model": model,
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": False, "top_n": top_n},
        }
        return await self._post_json(
            _DASHSCOPE_NATIVE,
            payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )

    async def _openai_compatible(
        self,
        key: str,
        model: str,
        query: str,
        documents: list[str],
        top_n: int,
        timeout: int,
    ) -> dict[str, Any]:
        """OpenAI 风格 /reranks（含百炼 compatible-mode）。"""
        base = (
            settings.rerank_base_url
            or settings.embedding_base_url
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        url = f"{base}/reranks"
        payload = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        return await self._post_json(
            url,
            payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )

    async def _cohere(
        self,
        key: str,
        model: str,
        query: str,
        documents: list[str],
        top_n: int,
        timeout: int,
    ) -> dict[str, Any]:
        """Cohere v2 rerank。"""
        base = (settings.rerank_base_url or "https://api.cohere.com/v2").rstrip("/")
        url = f"{base}/rerank" if not base.endswith("/rerank") else base
        payload = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        return await self._post_json(
            url,
            payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )

    async def _jina(
        self,
        key: str,
        model: str,
        query: str,
        documents: list[str],
        top_n: int,
        timeout: int,
    ) -> dict[str, Any]:
        """Jina rerank。"""
        base = (settings.rerank_base_url or "https://api.jina.ai/v1/").rstrip("/") + "/"
        url = urljoin(base, "rerank")
        payload = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        return await self._post_json(
            url,
            payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        """统一 POST JSON。"""
        hdrs = {"Content-Type": "application/json", **headers}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=hdrs)
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("rerank response is not an object")
        return data

    def _parse_results(
        self, data: dict[str, Any], *, n_docs: int
    ) -> list[tuple[int, float]]:
        """兼容 output.results / results / data 三种包体。"""
        rows = (
            (data.get("output") or {}).get("results")
            if isinstance(data.get("output"), dict)
            else None
        )
        if not isinstance(rows, list):
            rows = data.get("results")
        if not isinstance(rows, list):
            rows = data.get("data")
        if not isinstance(rows, list):
            return []
        parsed: list[tuple[int, float]] = []
        seen: set[int] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("index"))
                score = float(
                    row.get("relevance_score", row.get("score", row.get("relevanceScore")))
                )
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= n_docs or idx in seen:
                continue
            seen.add(idx)
            parsed.append((idx, score))
        parsed.sort(key=lambda x: x[1], reverse=True)
        return parsed


rerank_service = RerankService()
