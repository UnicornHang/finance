"""RAG 检索服务：Embedding + 混合召回（向量/稀疏/RRF）+ Rerank。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessError
from app.core.security import decrypt_field
from app.models import LlmConfig
from app.services.milvus_service import milvus_kb_store
from app.services.providers import PROVIDERS
from app.services.rag_hybrid import (
    channel_source,
    display_score,
    load_chunks,
    reciprocal_rank_fusion,
    sparse_search,
)
from app.services.rerank_service import rerank_service

logger = logging.getLogger(__name__)

# 通义 Embedding 支持的输出维数（按模型取交集校验）
_DASHSCOPE_EMBED_DIMS_V3 = frozenset({64, 128, 256, 512, 768, 1024})
_DASHSCOPE_EMBED_DIMS_QWEN37 = frozenset({256, 512, 768, 1024, 1536, 2048, 2560})
_DASHSCOPE_DEFAULT_DIM = 1024
_DASHSCOPE_BASE = PROVIDERS["dashscope"]["base_url"]
# 单次请求条数上限（官方文档）
_DASHSCOPE_BATCH_QWEN37 = 20
_DASHSCOPE_BATCH_LEGACY = 10


def _dashscope_embed_dims(model: str) -> frozenset[int]:
    """按模型返回合法维数集合。"""
    name = (model or "").lower()
    if name.startswith("qwen3.7-text-embedding") or name.startswith("qwen3-text-embedding"):
        return _DASHSCOPE_EMBED_DIMS_QWEN37
    if name.startswith("text-embedding-v4"):
        return frozenset({64, 128, 256, 512, 768, 1024, 1536, 2048})
    return _DASHSCOPE_EMBED_DIMS_V3


def _dashscope_batch_size(model: str) -> int:
    """按模型返回批量 embedding 上限。"""
    name = (model or "").lower()
    if name.startswith("qwen3.7-text-embedding") or name.startswith("qwen3-text-embedding"):
        return _DASHSCOPE_BATCH_QWEN37
    return _DASHSCOPE_BATCH_LEGACY


class RAGService:
    """知识库检索。向量主路径走 Milvus；正文与关键词仍在 Postgres。"""

    async def _resolve_embed_endpoint(
        self,
        db: AsyncSession | None = None,
        tenant_id: str | UUID | None = None,
    ) -> dict[str, Any]:
        """解析 Embedding 调用参数：环境变量优先，否则回落已配置的 LLM 场景密钥。"""
        api_key = (
            settings.embedding_api_key
            or settings.llm_contract_api_key
            or settings.llm_chitchat_api_key
            or ""
        ).strip()
        base_url = (
            settings.embedding_base_url
            or settings.llm_contract_base_url
            or settings.llm_chitchat_base_url
            or "https://api.openai.com/v1"
        )
        model = settings.embedding_model
        provider = "openai"
        # 与 Milvus collection 维数对齐；通义场景可能下调
        dimension = settings.embedding_dimension

        if not api_key and db is not None and tenant_id is not None:
            # 直接查「有密钥且启用」的配置，避免同 scene 多行时拿到空 key 的旧 openai 行
            tid = UUID(str(tenant_id))
            result = await db.execute(
                select(LlmConfig)
                .where(
                    LlmConfig.tenant_id == tid,
                    LlmConfig.enabled.is_(True),
                    LlmConfig.api_key_encrypted.is_not(None),
                )
                .order_by(LlmConfig.updated_at.desc().nullslast())
                .limit(8)
            )
            for cfg in result.scalars().all():
                raw = decrypt_field(cfg.api_key_encrypted) if cfg.api_key_encrypted else ""
                if not (raw or "").strip():
                    continue
                api_key = raw.strip()
                provider = (cfg.provider or "openai").lower()
                raw_base = (cfg.base_url or "").strip()
                if raw_base.startswith("http://") or raw_base.startswith("https://"):
                    base_url = raw_base
                elif provider == "dashscope":
                    base_url = _DASHSCOPE_BASE
                logger.info(
                    "embedding credentials from llm_configs scene=%s provider=%s",
                    cfg.scene,
                    provider,
                )
                break

        if not api_key:
            raise BusinessError(
                "未配置 Embedding API Key（EMBEDDING_API_KEY / LLM_*_API_KEY / 管理端 LLM 密钥）",
                code="KB_EMBEDDING_NOT_CONFIGURED",
            )

        # 通义兼容网关：修正 base_url / 旧 OpenAI 模型名 / 维数
        if "dashscope" in (base_url or "").lower() or provider == "dashscope":
            provider = "dashscope"
            if "openai.com" in (base_url or "") or not (base_url or "").startswith("http"):
                base_url = _DASHSCOPE_BASE
            # 仅把 OpenAI 旧名映射到通义；显式配置的 qwen3.7 / v3 / v4 原样保留
            if model.startswith("text-embedding-3") or model.startswith("text-embedding-ada"):
                model = "text-embedding-v3"
            allowed_dims = _dashscope_embed_dims(model)
            if dimension not in allowed_dims:
                logger.warning(
                    "EMBEDDING_DIMENSION=%s 不被 %s 支持，改用 %s",
                    dimension,
                    model,
                    _DASHSCOPE_DEFAULT_DIM,
                )
                dimension = _DASHSCOPE_DEFAULT_DIM

        return {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "provider": provider,
            "dimension": dimension,
        }

    def _client_from(self, endpoint: dict[str, Any]) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=endpoint["api_key"], base_url=endpoint["base_url"])

    async def _embed_call(
        self,
        texts: list[str] | str,
        *,
        db: AsyncSession | None = None,
        tenant_id: str | UUID | None = None,
    ) -> list[list[float]]:
        """统一 embedding 调用，尽量带上 dimensions 以匹配 Milvus 维数。"""
        endpoint = await self._resolve_embed_endpoint(db, tenant_id)
        client = self._client_from(endpoint)
        expect_dim = int(endpoint["dimension"])
        kwargs: dict[str, Any] = {
            "model": endpoint["model"],
            "input": texts,
            "dimensions": expect_dim,
        }
        # OpenAI / 通义兼容网关支持 dimensions；个别网关失败则去掉重试
        try:
            response = await client.embeddings.create(**kwargs)
        except Exception:
            kwargs.pop("dimensions", None)
            response = await client.embeddings.create(**kwargs)
        ordered = sorted(response.data, key=lambda d: d.index)
        vectors = [d.embedding for d in ordered]
        if vectors and len(vectors[0]) != expect_dim:
            raise BusinessError(
                f"Embedding 维数 {len(vectors[0])} 与期望 {expect_dim} 不一致，"
                "请调整 EMBEDDING_DIMENSION 并重建同维 Milvus collection",
                code="KB_EMBED_DIM_MISMATCH",
            )
        return vectors

    async def embed(
        self,
        text_content: str,
        *,
        db: AsyncSession | None = None,
        tenant_id: str | UUID | None = None,
    ) -> list[float]:
        """文本转向量。"""
        vectors = await self._embed_call(text_content, db=db, tenant_id=tenant_id)
        return vectors[0]

    async def embed_batch(
        self,
        texts: list[str],
        *,
        db: AsyncSession | None = None,
        tenant_id: str | UUID | None = None,
    ) -> list[list[float]]:
        """批量转向量。"""
        if not texts:
            return []
        endpoint = await self._resolve_embed_endpoint(db, tenant_id)
        batch_size = 32
        if endpoint.get("provider") == "dashscope":
            batch_size = _dashscope_batch_size(str(endpoint.get("model") or ""))
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            out.extend(await self._embed_call(batch, db=db, tenant_id=tenant_id))
        return out

    async def retrieve(
        self,
        db: AsyncSession,
        question: str,
        tenant_id: str,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[dict]:
        """向量 + 稀疏混合召回，RRF 融合后再 Rerank 截断到 top_k。"""
        q = (question or "").strip()
        if not q or top_k <= 0:
            return []

        recall_k = max(top_k, top_k * max(1, settings.rag_retrieve_multiplier))
        q_emb = await self.embed(q, db=db, tenant_id=tenant_id)

        vector_task = self._vector_search(db, q_emb, tenant_id, recall_k, doc_type)
        if settings.rag_hybrid_enabled:
            vec_raw, sparse_raw = await asyncio.gather(
                vector_task,
                sparse_search(db, q, tenant_id, recall_k, doc_type),
                return_exceptions=True,
            )
            if isinstance(vec_raw, BaseException):
                raise vec_raw
            vector_hits = vec_raw
            if isinstance(sparse_raw, BaseException):
                logger.error("sparse retrieve failed", exc_info=sparse_raw)
                sparse_hits = []
            else:
                sparse_hits = sparse_raw
        else:
            vector_hits = await vector_task
            sparse_hits = []

        merged = await self._merge_channels(db, vector_hits, sparse_hits)
        if not merged:
            return []

        rrf_k = max(1, settings.rag_rrf_k)
        rrf = reciprocal_rank_fusion(
            [
                [h["chunk_id"] for h in vector_hits],
                [h["chunk_id"] for h in sparse_hits],
            ],
            k=rrf_k,
        )
        for cid, item in merged.items():
            item["rrf_score"] = rrf.get(cid, 0.0)
            item["score"] = display_score(
                vector_score=item.get("vector_score"),
                sparse_score=item.get("sparse_score"),
                rerank_score=None,
            )
            item["reranked"] = False

        ranked = sorted(
            merged.values(),
            key=lambda x: (x.get("rrf_score") or 0.0, x.get("score") or 0.0),
            reverse=True,
        )
        cand_n = max(top_k, min(settings.rag_rerank_candidates, len(ranked)))
        candidates = ranked[:cand_n]
        candidates = await self._apply_rerank(q, candidates)
        return candidates[:top_k]

    async def _vector_search(
        self,
        db: AsyncSession,
        q_emb: list[float],
        tenant_id: str,
        top_k: int,
        doc_type: str | None,
    ) -> list[dict]:
        """Milvus 向量召回，失败则 pgvector。"""
        try:
            return await asyncio.to_thread(
                milvus_kb_store.search,
                q_emb,
                tenant_id=tenant_id,
                top_k=top_k,
                doc_type=doc_type,
            )
        except BusinessError:
            logger.exception("milvus retrieve failed, try pgvector fallback")
            return await self._pgvector_search(db, q_emb, tenant_id, top_k, doc_type)

    async def _merge_channels(
        self,
        db: AsyncSession,
        vector_hits: list[dict],
        sparse_hits: list[dict],
    ) -> dict[str, dict]:
        """按 chunk_id 合并两路命中并回表补正文。"""
        vector_map = {h["chunk_id"]: h for h in vector_hits if h.get("chunk_id")}
        sparse_map = {h["chunk_id"]: h for h in sparse_hits if h.get("chunk_id")}
        all_ids = list(dict.fromkeys([*vector_map.keys(), *sparse_map.keys()]))
        need_load: list[UUID] = []
        for cid in all_ids:
            sparse = sparse_map.get(cid)
            if not sparse or not sparse.get("content"):
                need_load.append(UUID(cid))
        content_map = await load_chunks(db, need_load)

        merged: dict[str, dict] = {}
        for cid in all_ids:
            vh = vector_map.get(cid)
            sh = sparse_map.get(cid)
            meta = content_map.get(cid) or {}
            content = (sh or {}).get("content") or meta.get("content")
            if not content:
                continue
            merged[cid] = {
                "chunk_id": cid,
                "doc_id": (sh or {}).get("doc_id")
                or meta.get("doc_id")
                or (vh or {}).get("doc_id"),
                "title": (sh or {}).get("title") or meta.get("title"),
                "doc_type": (sh or {}).get("doc_type") or meta.get("doc_type"),
                "content": content,
                "vector_score": float(vh["score"])
                if vh and vh.get("score") is not None
                else None,
                "sparse_score": (sh or {}).get("sparse_score"),
                "source": channel_source(vh is not None, sh is not None),
            }
        return merged

    async def _apply_rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """有密钥则交叉编码精排；失败保持 RRF 顺序。"""
        if not candidates or not rerank_service.available():
            return candidates
        max_chars = max(200, settings.rerank_max_doc_chars)
        docs: list[str] = []
        for item in candidates:
            title = (item.get("title") or "").strip()
            body = (item.get("content") or "").strip()
            blob = f"{title}\n{body}".strip() if title else body
            docs.append(blob[:max_chars])
        ranked = await rerank_service.rerank(query, docs, top_n=len(docs))
        if not ranked:
            return candidates
        by_idx = {idx: score for idx, score in ranked}
        ordered: list[dict] = []
        for idx, score in ranked:
            item = dict(candidates[idx])
            item["rerank_score"] = score
            item["score"] = display_score(
                vector_score=item.get("vector_score"),
                sparse_score=item.get("sparse_score"),
                rerank_score=score,
            )
            item["reranked"] = True
            ordered.append(item)
        for i, item in enumerate(candidates):
            if i not in by_idx:
                ordered.append(item)
        return ordered

    async def _pgvector_search(
        self,
        db: AsyncSession,
        q_emb: list[float],
        tenant_id: str,
        top_k: int,
        doc_type: str | None,
    ) -> list[dict]:
        """Milvus 不可用时的降级：走 Postgres pgvector（若列仍有向量）。"""
        emb_str = "[" + ",".join(str(x) for x in q_emb) + "]"
        type_clause = "AND d.doc_type = :doc_type" if doc_type else ""
        params: dict = {"emb": emb_str, "tenant_id": tenant_id, "top_k": top_k}
        if doc_type:
            params["doc_type"] = doc_type
        sql = text(
            f"""
            SELECT c.id AS chunk_id, c.doc_id,
                   1 - (c.embedding <=> :emb::vector) AS score
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.doc_id
            WHERE d.status = 'active'
              AND c.embedding IS NOT NULL
              AND (c.tenant_id = CAST(:tenant_id AS uuid) OR c.tenant_id IS NULL)
              {type_clause}
            ORDER BY c.embedding <=> :emb::vector
            LIMIT :top_k
            """
        )
        try:
            rows = (await db.execute(sql, params)).fetchall()
        except Exception:
            logger.exception("pgvector fallback failed")
            return []
        return [
            {
                "chunk_id": str(row.chunk_id),
                "doc_id": str(row.doc_id),
                "score": float(row.score),
                "source": "vector",
            }
            for row in rows
        ]

    async def retrieve_rules(self, db: AsyncSession, tenant_id: str) -> list[str]:
        """检索合规规则片段。"""
        results = await self.retrieve(
            db,
            "合同合规审查规则 盖章 付款 违约 争议解决",
            tenant_id,
            top_k=10,
            doc_type="rule",
        )
        if not results:
            results = await self.retrieve(
                db, "合同合规审查规则", tenant_id, top_k=8, doc_type=None
            )
        return [r["content"] for r in results]


rag_service = RAGService()
