"""知识库索引替换事务：切分、向量化、PG 写入与 Milvus 补偿。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import ChunkDraft, SplitConfig, config_to_params, run_split
from app.chunking.types import StrategyName
from app.config import settings
from app.core.exceptions import BusinessError
from app.models import KbChunk, KbDocument
from app.services.milvus_service import milvus_kb_store
from app.services.rag_service import rag_service
from app.services.rag_tokenize import to_search_tokens

logger = logging.getLogger(__name__)


async def index_kb_document(
    db: AsyncSession,
    row: KbDocument,
    *,
    bump_version: bool,
    embed_tenant_id: UUID,
    config: SplitConfig,
) -> None:
    """无中断重建索引；失败回滚新数据并保留旧索引。"""
    row = (
        await db.execute(
            select(KbDocument)
            .where(KbDocument.id == row.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    old_ids = list(
        (
            await db.execute(
                select(KbChunk.id).where(KbChunk.doc_id == row.id)
            )
        ).scalars()
    )
    new_milvus_ids: list[UUID] = []
    milvus_rows: list[dict[str, Any]] = []
    milvus_attempted = False
    try:
        drafts, effective, fallback = await _split_document(
            db,
            row,
            config,
            embed_tenant_id,
        )
        embed_texts = [draft.content for draft in drafts if draft.embeddable]
        embeddings = await rag_service.embed_batch(
            embed_texts,
            db=db,
            tenant_id=embed_tenant_id,
        )
        if len(embeddings) != len(embed_texts):
            raise BusinessError(
                "向量化结果数量不匹配",
                code="KB_EMBED_MISMATCH",
            )

        local_rows = await _insert_chunks(
            db,
            row,
            drafts,
            embeddings,
        )
        milvus_rows = _build_milvus_rows(
            row,
            drafts,
            embeddings,
            local_rows,
        )
        if milvus_kb_store.enabled:
            new_milvus_ids = [item["chunk_id"] for item in milvus_rows]
            milvus_attempted = True
            await asyncio.to_thread(
                milvus_kb_store.upsert_chunks,
                milvus_rows,
            )
        elif not settings.kb_store_pg_embedding:
            raise BusinessError(
                "Milvus 未启用且未开启 PG 向量备份，无法完成索引",
                code="KB_VECTOR_STORE_REQUIRED",
            )

        if old_ids:
            await db.execute(delete(KbChunk).where(KbChunk.id.in_(old_ids)))
        _activate_document(
            row,
            config=config,
            effective=effective,
            fallback=fallback,
            drafts=drafts,
            bump_version=bump_version,
        )
        await db.commit()
    except Exception as exc:
        await _rollback_new_index(
            db,
            row.id,
            new_milvus_ids,
            milvus_attempted,
        )
        if isinstance(exc, BusinessError):
            raise
        raise BusinessError(
            f"向量化失败：{exc}",
            code="KB_INDEX_FAILED",
        ) from exc

    await _cleanup_old_vectors(row.id, old_ids)
    logger.info(
        "kb indexed id=%s retrieval_chunks=%s strategy=%s milvus=%s",
        row.id,
        row.chunk_count,
        config.strategy,
        milvus_kb_store.enabled,
    )


async def _split_document(
    db: AsyncSession,
    row: KbDocument,
    config: SplitConfig,
    tenant_id: UUID,
) -> tuple[list[ChunkDraft], StrategyName, str | None]:
    """执行配置策略；语义策略复用租户 Embedding 端点。"""

    async def embed_sentences(texts: list[str]) -> list[list[float]]:
        """批量生成语义切分需要的句向量。"""
        return await rag_service.embed_batch(
            texts,
            db=db,
            tenant_id=tenant_id,
        )

    drafts, effective, fallback = await run_split(
        row.content or "",
        filename=row.source_file,
        config=config,
        embed_fn=embed_sentences,
    )
    if fallback:
        logger.warning(
            "kb split fallback id=%s from=%s to=%s reason=%s",
            row.id,
            config.strategy,
            effective,
            fallback,
        )
    if not drafts:
        raise BusinessError("切分结果为空", code="KB_EMPTY_CONTENT")
    return drafts, effective, fallback


async def _insert_chunks(
    db: AsyncSession,
    row: KbDocument,
    drafts: list[ChunkDraft],
    embeddings: list[list[float]],
) -> dict[int, KbChunk]:
    """插入新版 PG 切块并建立子块到父块的关联。"""
    embedding_iter = iter(embeddings)
    local_rows: dict[int, KbChunk] = {}
    for index, draft in enumerate(drafts):
        embedding = next(embedding_iter) if draft.embeddable else None
        chunk = KbChunk(
            doc_id=row.id,
            tenant_id=row.tenant_id,
            chunk_index=index,
            role=draft.role,
            section_path=draft.section_path or None,
            embeddable=draft.embeddable,
            content=draft.content,
            search_tokens=(
                to_search_tokens(draft.content, title=row.title)
                if draft.embeddable
                else None
            ),
            embedding=(
                embedding
                if embedding and settings.kb_store_pg_embedding
                else None
            ),
            token_count=len(draft.content),
            metadata_={
                "title": row.title,
                "doc_type": row.doc_type,
                "page_no": draft.page_no,
            },
        )
        db.add(chunk)
        local_rows[draft.local_id] = chunk
    await db.flush()
    for draft in drafts:
        if draft.parent_local_id is None:
            continue
        parent = local_rows.get(draft.parent_local_id)
        if parent is not None:
            local_rows[draft.local_id].parent_id = parent.id
    await db.flush()
    return local_rows


def _build_milvus_rows(
    row: KbDocument,
    drafts: list[ChunkDraft],
    embeddings: list[list[float]],
    local_rows: dict[int, KbChunk],
) -> list[dict[str, Any]]:
    """把可检索块转换为 Milvus 写入结构。"""
    rows: list[dict[str, Any]] = []
    embedding_iter = iter(embeddings)
    for draft in drafts:
        if not draft.embeddable:
            continue
        rows.append(
            {
                "chunk_id": local_rows[draft.local_id].id,
                "doc_id": row.id,
                "tenant_id": row.tenant_id,
                "doc_type": row.doc_type or "policy",
                "embedding": next(embedding_iter),
            }
        )
    return rows


def _activate_document(
    row: KbDocument,
    *,
    config: SplitConfig,
    effective: StrategyName,
    fallback: str | None,
    drafts: list[ChunkDraft],
    bump_version: bool,
) -> None:
    """写入成功后的文档状态与可验收统计。"""
    row.chunk_count = sum(1 for draft in drafts if draft.embeddable)
    row.embedding_model = settings.embedding_model
    row.chunk_strategy = config.strategy
    row.chunk_strategy_effective = effective
    row.chunk_params = config_to_params(
        config,
        fallback_reason=fallback,
        drafts=drafts,
    )
    row.status = "active"
    row.error_message = None
    if bump_version:
        row.version = (row.version or 1) + 1


async def _rollback_new_index(
    db: AsyncSession,
    doc_id: UUID,
    new_milvus_ids: list[UUID],
    milvus_attempted: bool,
) -> None:
    """回滚 PG；若新向量已尝试写入，则精确补偿删除。"""
    logger.exception("kb index failed id=%s", doc_id)
    await db.rollback()
    if not milvus_attempted or not new_milvus_ids:
        return
    try:
        await asyncio.to_thread(
            milvus_kb_store.delete_by_chunk_ids,
            new_milvus_ids,
        )
    except Exception:
        logger.exception("kb new vector compensation failed id=%s", doc_id)


async def _cleanup_old_vectors(
    doc_id: UUID,
    old_ids: list[UUID],
) -> None:
    """提交 PG 后精确清旧向量；失败不破坏已经可用的新向量。"""
    if not milvus_kb_store.enabled or not old_ids:
        return
    for attempt in range(2):
        try:
            await asyncio.to_thread(
                milvus_kb_store.delete_by_chunk_ids,
                old_ids,
            )
            return
        except BusinessError:
            logger.exception(
                "kb stale vector cleanup attempt=%s failed id=%s",
                attempt + 1,
                doc_id,
            )
    logger.error(
        "kb stale vectors remain id=%s count=%s",
        doc_id,
        len(old_ids),
    )
