"""Milvus 向量库：知识库 chunk 的写入、删除与近似检索。

Postgres 保留文档正文与元数据；向量检索以 Milvus 为准（企业级 Agent 默认路径）。
"""

from __future__ import annotations

import logging
import threading
from typing import Any
from uuid import UUID

from app.config import settings
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

# 通用文档在过滤表达式里用空串（标量字段不使用 NULL）
GLOBAL_TENANT_TOKEN = ""


def _tenant_token(tenant_id: UUID | str | None) -> str:
    if tenant_id is None:
        return GLOBAL_TENANT_TOKEN
    return str(tenant_id)


class MilvusKbStore:
    """知识库专用 Milvus Collection 封装（同步 SDK，调用方可用 asyncio.to_thread）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = False

    @property
    def enabled(self) -> bool:
        return bool(settings.milvus_enabled)

    def _connect_and_ensure(self) -> None:
        """建立连接并确保 collection / index 存在。"""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            if not self.enabled:
                raise BusinessError(
                    "Milvus 未启用（MILVUS_ENABLED=false）",
                    code="MILVUS_DISABLED",
                )
            try:
                from pymilvus import (
                    Collection,
                    CollectionSchema,
                    DataType,
                    FieldSchema,
                    connections,
                    utility,
                )
            except ImportError as exc:
                raise BusinessError(
                    "未安装 pymilvus，请执行 pip install 'pymilvus>=2.4.0'",
                    code="MILVUS_SDK_MISSING",
                ) from exc

            try:
                connections.connect(
                    alias="default",
                    host=settings.milvus_host,
                    port=str(settings.milvus_port),
                    user=settings.milvus_user or "",
                    password=settings.milvus_password or "",
                )
            except Exception as exc:
                raise BusinessError(
                    f"连接 Milvus 失败（{settings.milvus_host}:{settings.milvus_port}）：{exc}",
                    code="MILVUS_CONNECT_FAILED",
                ) from exc

            name = settings.milvus_collection
            dim = settings.embedding_dimension
            if not utility.has_collection(name):
                fields = [
                    FieldSchema(
                        name="chunk_id",
                        dtype=DataType.VARCHAR,
                        is_primary=True,
                        max_length=36,
                        auto_id=False,
                    ),
                    FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=36),
                    FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=36),
                    FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
                ]
                schema = CollectionSchema(
                    fields=fields,
                    description="Finance AI knowledge base chunks",
                )
                col = Collection(name=name, schema=schema)
                col.create_index(
                    field_name="embedding",
                    index_params={
                        "index_type": settings.milvus_index_type,
                        "metric_type": settings.milvus_metric_type,
                        "params": {"nlist": settings.milvus_nlist},
                    },
                )
                logger.info("milvus collection created name=%s dim=%s", name, dim)
            col = Collection(name)
            col.load()
            self._ready = True
            logger.info(
                "milvus ready host=%s:%s collection=%s",
                settings.milvus_host,
                settings.milvus_port,
                name,
            )

    def _collection(self):
        from pymilvus import Collection

        self._connect_and_ensure()
        return Collection(settings.milvus_collection)

    def upsert_chunks(self, rows: list[dict[str, Any]]) -> None:
        """插入 chunk 向量（调用方应先 delete_by_doc_id）。"""
        if not rows:
            return
        col = self._collection()
        chunk_ids = [str(r["chunk_id"]) for r in rows]
        doc_ids = [str(r["doc_id"]) for r in rows]
        tenant_ids = [_tenant_token(r.get("tenant_id")) for r in rows]
        doc_types = [(r.get("doc_type") or "policy")[:64] for r in rows]
        embeddings = [list(map(float, r["embedding"])) for r in rows]
        col.insert([chunk_ids, doc_ids, tenant_ids, doc_types, embeddings])
        col.flush()
        logger.info("milvus inserted chunks=%s", len(rows))

    def delete_by_doc_id(self, doc_id: UUID | str) -> None:
        """按文档删除全部向量。"""
        if not self.enabled:
            return
        try:
            col = self._collection()
            did = str(doc_id)
            col.delete(f'doc_id == "{did}"')
            col.flush()
            logger.info("milvus deleted doc_id=%s", did)
        except BusinessError:
            raise
        except Exception as exc:
            logger.exception("milvus delete failed doc_id=%s", doc_id)
            raise BusinessError(
                f"Milvus 删除向量失败：{exc}",
                code="MILVUS_DELETE_FAILED",
            ) from exc

    def search(
        self,
        embedding: list[float],
        *,
        tenant_id: str,
        top_k: int = 10,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """近似检索。score 越大越相关（由 distance 换算）。"""
        col = self._collection()
        filt = f'(tenant_id == "{tenant_id}" or tenant_id == "{GLOBAL_TENANT_TOKEN}")'
        if doc_type:
            safe = doc_type.replace('"', "")
            filt = f'({filt}) and doc_type == "{safe}"'

        results = col.search(
            data=[list(map(float, embedding))],
            anns_field="embedding",
            param={
                "metric_type": settings.milvus_metric_type,
                "params": {"nprobe": settings.milvus_nprobe},
            },
            limit=top_k,
            expr=filt,
            output_fields=["chunk_id", "doc_id", "tenant_id", "doc_type"],
        )
        hits: list[dict[str, Any]] = []
        if not results:
            return hits
        metric = settings.milvus_metric_type.upper()
        for hit in results[0]:
            raw = float(hit.distance)
            if metric == "COSINE":
                # Milvus COSINE：hit.distance 本身就是相似度（越大越相关，约 [-1, 1]）
                # 切勿再做 1-distance，否则会把排序完全反转
                score = max(0.0, raw)
            elif metric == "IP":
                score = raw
            else:
                # L2 等：distance 越小越近
                score = 1.0 / (1.0 + raw)
            entity = hit.entity
            hits.append(
                {
                    "chunk_id": str(entity.get("chunk_id") or hit.id),
                    "doc_id": str(entity.get("doc_id") or ""),
                    "tenant_id": entity.get("tenant_id"),
                    "doc_type": entity.get("doc_type"),
                    "score": float(score),
                    "source": "vector",
                }
            )
        return hits


milvus_kb_store = MilvusKbStore()
