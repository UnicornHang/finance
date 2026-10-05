"""混合检索：Postgres 稀疏召回 + RRF 融合 + 展示分。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KbChunk, KbDocument
from app.services.rag_tokenize import keyword_terms, query_tokens, to_or_tsquery

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
) -> dict[str, float]:
    """RRF：多路排名倒数融合，只依赖名次不依赖原始分数量纲。"""
    scores: dict[str, float] = {}
    for ranked in ranked_id_lists:
        seen: set[str] = set()
        rank = 0
        for cid in ranked:
            if not cid or cid in seen:
                continue
            seen.add(cid)
            rank += 1
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


def channel_source(in_vector: bool, in_sparse: bool) -> str:
    """标记命中了哪些召回路。"""
    if in_vector and in_sparse:
        return "hybrid"
    if in_vector:
        return "vector"
    if in_sparse:
        return "keyword"
    return "unknown"


def rank_to_unit_score(rank: int) -> float:
    """名次映射到 (0, 1]，供无向量分时的门槛判断。"""
    if rank < 1:
        return 0.0
    return 1.0 / (1.0 + 0.12 * (rank - 1))


def display_score(
    *,
    vector_score: float | None,
    sparse_score: float | None,
    rerank_score: float | None,
) -> float:
    """下游门槛用的最终分：优先 Rerank，否则向量/稀疏加权。"""
    if rerank_score is not None:
        return max(0.0, min(1.0, float(rerank_score)))
    has_v = vector_score is not None
    has_s = sparse_score is not None
    if has_v and has_s:
        return 0.6 * float(vector_score) + 0.4 * float(sparse_score)
    if has_v:
        return float(vector_score)
    if has_s:
        return float(sparse_score)
    return 0.0


def normalize_rerank_scores(scores: list[float]) -> list[float]:
    """已在 [0,1] 则原样；否则对本批做 min-max，避免 logits 打穿门槛。"""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if lo >= 0.0 and hi <= 1.0:
        return [float(s) for s in scores]
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(float(s) - lo) / (hi - lo) for s in scores]


async def load_chunks(
    db: AsyncSession, chunk_ids: list[UUID]
) -> dict[str, dict[str, Any]]:
    """按 id 批量取正文与标题。"""
    if not chunk_ids:
        return {}
    result = await db.execute(
        select(
            KbChunk.id,
            KbChunk.doc_id,
            KbChunk.content,
            KbDocument.title,
            KbDocument.doc_type,
        )
        .join(KbDocument, KbDocument.id == KbChunk.doc_id)
        .where(KbChunk.id.in_(chunk_ids), KbDocument.status == "active")
    )
    out: dict[str, dict[str, Any]] = {}
    for row in result.all():
        out[str(row.id)] = {
            "doc_id": str(row.doc_id),
            "content": row.content,
            "title": row.title,
            "doc_type": row.doc_type,
        }
    return out


async def sparse_search(
    db: AsyncSession,
    question: str,
    tenant_id: str,
    top_k: int,
    doc_type: str | None,
) -> list[dict[str, Any]]:
    """稀疏召回：优先 tsvector OR 匹配，空结果再 ILIKE。"""
    if top_k <= 0:
        return []
    hits = await _fts_search(db, question, tenant_id, top_k, doc_type)
    if hits:
        return hits
    return await _ilike_search(db, question, tenant_id, top_k, doc_type)


def _tenant_type_sql(doc_type: str | None) -> str:
    extra = "AND d.doc_type = :doc_type" if doc_type else ""
    return f"""
        FROM kb_chunks c
        JOIN kb_documents d ON d.id = c.doc_id
        WHERE d.status = 'active'
          AND (c.tenant_id = CAST(:tenant_id AS uuid) OR c.tenant_id IS NULL)
          {extra}
    """


async def _fts_search(
    db: AsyncSession,
    question: str,
    tenant_id: str,
    top_k: int,
    doc_type: str | None,
) -> list[dict[str, Any]]:
    """Postgres simple 全文：search_tokens 经 generated tsvector。"""
    qstr = to_or_tsquery(query_tokens(question))
    if not qstr:
        return []
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "top_k": top_k,
        "q": qstr,
    }
    if doc_type:
        params["doc_type"] = doc_type
    sql = text(
        f"""
        SELECT c.id, c.doc_id, c.content, d.title, d.doc_type,
               ts_rank_cd(c.search_tsv, to_tsquery('simple', :q)) AS rank
        {_tenant_type_sql(doc_type)}
          AND c.search_tsv @@ to_tsquery('simple', :q)
        ORDER BY rank DESC, c.created_at DESC
        LIMIT :top_k
        """
    )
    try:
        rows = (await db.execute(sql, params)).fetchall()
    except Exception:
        logger.exception("fts sparse retrieve failed")
        return []
    return _rows_to_sparse_hits(rows)


async def _ilike_search(
    db: AsyncSession,
    question: str,
    tenant_id: str,
    top_k: int,
    doc_type: str | None,
) -> list[dict[str, Any]]:
    """未建 search_tokens 的旧切片回退。"""
    keywords = keyword_terms(question)
    if not keywords:
        return []
    like_params: dict[str, Any] = {"tenant_id": tenant_id, "top_k": top_k}
    like_clauses: list[str] = []
    for i, kw in enumerate(keywords):
        key = f"kw{i}"
        like_clauses.append(f"c.content ILIKE :{key}")
        like_params[key] = f"%{kw}%"
    if doc_type:
        like_params["doc_type"] = doc_type
    sql = text(
        f"""
        SELECT c.id, c.doc_id, c.content, d.title, d.doc_type,
               0.5 AS rank
        {_tenant_type_sql(doc_type)}
          AND ({' OR '.join(like_clauses)})
        LIMIT :top_k
        """
    )
    try:
        rows = (await db.execute(sql, like_params)).fetchall()
    except Exception:
        logger.exception("ilike sparse retrieve failed")
        return []
    return _rows_to_sparse_hits(rows)


def _rows_to_sparse_hits(rows: list[Any]) -> list[dict[str, Any]]:
    """把 SQL 行转成统一稀疏命中结构。"""
    hits: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        hits.append(
            {
                "chunk_id": str(row.id),
                "doc_id": str(row.doc_id),
                "title": row.title,
                "doc_type": row.doc_type,
                "content": row.content,
                "sparse_rank": float(row.rank or 0.0),
                "sparse_score": rank_to_unit_score(i),
            }
        )
    return hits
