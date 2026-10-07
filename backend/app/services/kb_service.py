"""知识库文档服务：上传解析、切分向量化、列表/删除/重索引。"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import (
    CHILD_SIZE_DEFAULT,
    OVERLAP_DEFAULT,
    PARENT_SIZE_DEFAULT,
    RECURSIVE_SIZE_DEFAULT,
    SEMANTIC_THRESHOLD_DEFAULT,
    SplitConfig,
    chunk_strategy_catalog,
    config_to_params,
    normalize_split_config,
)
from app.config import settings
from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.models import KbChunk, KbDocument, User
from app.services.audit_service import write_audit_log
from app.services.invoice_document import _extract_file_text, _guess_mime
from app.services.kb_indexing import index_kb_document
from app.services.milvus_service import milvus_kb_store

CHUNK_SIZE = RECURSIVE_SIZE_DEFAULT
CHUNK_OVERLAP = OVERLAP_DEFAULT
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf", ".docx", ".doc"}


def extract_document_text(
    file_bytes: bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> str:
    """从上传文件抽出纯文本。"""
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise BusinessError(
            "文件过大，单份知识库文档请控制在 8MB 以内",
            code="KB_FILE_TOO_LARGE",
        )
    name = (filename or "").lower()
    suffix = f".{name.rsplit('.', 1)[-1]}" if "." in name else ""
    if suffix and suffix not in ALLOWED_SUFFIXES:
        raise BusinessError(
            "仅支持 txt / md / pdf / doc / docx",
            code="KB_FILE_TYPE_UNSUPPORTED",
        )
    mime = _guess_mime(file_bytes, content_type, filename)
    if suffix in {".txt", ".md", ".markdown"} or mime.startswith("text/"):
        text = ""
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                text = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    else:
        text = _extract_file_text(file_bytes, mime, filename)
    text = (text or "").strip()
    if len(text) < 20:
        raise BusinessError("未能从文件中读出有效正文", code="KB_EMPTY_CONTENT")
    return text


class KbService:
    """知识库 CRUD + 索引。"""

    def _assert_admin(self, user: User) -> None:
        if user.role != "admin":
            raise ForbiddenError("仅管理员可管理知识库", code="KB_FORBIDDEN")

    def _serialize(self, row: KbDocument) -> dict[str, Any]:
        params = row.chunk_params if isinstance(row.chunk_params, dict) else {}
        return {
            "id": str(row.id),
            "title": row.title,
            "doc_type": row.doc_type,
            "status": row.status,
            "chunk_count": row.chunk_count or 0,
            "version": row.version or 1,
            "error_message": row.error_message,
            "source_file": row.source_file,
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
            "chunk_strategy": row.chunk_strategy,
            "chunk_strategy_effective": row.chunk_strategy_effective,
            "chunk_params": params,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def get_document_detail(
        self,
        db: AsyncSession,
        *,
        user: "User",
        doc_id: UUID,
    ) -> dict[str, Any]:
        """文档预览：元数据 + 全文 + 切分块列表。"""
        self._assert_admin(user)

        row = await self.get_document(db, user=user, doc_id=doc_id)
        result = await db.execute(
            select(KbChunk)
            .where(KbChunk.doc_id == row.id)
            .order_by(KbChunk.chunk_index.asc())
            .limit(400)
        )
        chunks = [
            {
                "id": str(c.id),
                "chunk_index": c.chunk_index,
                "content": c.content,
                "token_count": c.token_count,
                "role": c.role or "leaf",
                "parent_id": str(c.parent_id) if c.parent_id else None,
                "section_path": c.section_path,
                "embeddable": bool(c.embeddable),
            }
            for c in result.scalars().all()
        ]
        detail = self._serialize(row)
        detail["content"] = row.content or ""
        detail["embedding_model"] = row.embedding_model
        detail["chunks"] = chunks
        return detail

    async def list_documents(
        self,
        db: AsyncSession,
        *,
        user: "User",
    ) -> list[dict[str, Any]]:
        """当前租户文档 + 通用文档。"""
        self._assert_admin(user)

        result = await db.execute(
            select(KbDocument)
            .where(
                or_(
                    KbDocument.tenant_id == user.tenant_id,
                    KbDocument.tenant_id.is_(None),
                )
            )
            .order_by(KbDocument.created_at.desc())
            .limit(200)
        )
        return [self._serialize(row) for row in result.scalars().all()]

    async def get_document(
        self,
        db: AsyncSession,
        *,
        user: "User",
        doc_id: UUID,
    ) -> KbDocument:
        """读取单份文档并校验可见性。"""
        row = await db.get(KbDocument, doc_id)
        if row is None:
            raise NotFoundError("文档不存在", code="KB_NOT_FOUND")
        if row.tenant_id is not None and row.tenant_id != user.tenant_id:
            raise ForbiddenError("无权访问该文档", code="KB_FORBIDDEN")
        return row

    def get_index_settings(self) -> dict[str, Any]:
        """返回上传弹窗用的默认索引参数。"""
        return {
            "chunk_size": CHILD_SIZE_DEFAULT,
            "chunk_overlap": OVERLAP_DEFAULT,
            "parent_size": PARENT_SIZE_DEFAULT,
            "chunk_strategy": "parent_child",
            "semantic_threshold": SEMANTIC_THRESHOLD_DEFAULT,
            "chunk_strategies": chunk_strategy_catalog(),
            "embedding_model": settings.embedding_model,
            "embedding_dimension": settings.embedding_dimension,
            "embedding_base_url": settings.embedding_base_url,
            "index_mode": "high_quality",
            "index_modes": [
                {
                    "value": "high_quality",
                    "label": "高质量（混合检索）",
                    "description": "切分后 Embedding 入 Milvus，并写稀疏词供 RRF + Rerank",
                },
                {
                    "value": "economy",
                    "label": "经济（关键词）",
                    "description": "暂未开放；当前仅支持向量索引",
                    "disabled": True,
                },
            ],
            "retrieve_top_k": 5,
            "hybrid_enabled": settings.rag_hybrid_enabled,
            "rerank_enabled": settings.rag_rerank_enabled,
            "rerank_model": settings.rerank_model,
            "milvus_enabled": milvus_kb_store.enabled,
            "allowed_suffixes": sorted(ALLOWED_SUFFIXES),
            "max_upload_bytes": MAX_UPLOAD_BYTES,
        }

    async def upload_document(
        self,
        db: AsyncSession,
        *,
        user: User,
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        title: str | None = None,
        doc_type: str | None = None,
        is_global: bool = False,
        chunk_strategy: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        parent_size: int | None = None,
        semantic_threshold: float | None = None,
    ) -> dict[str, Any]:
        """上传并同步完成切分向量化。"""
        self._assert_admin(user)
        cfg = normalize_split_config(
            strategy=chunk_strategy,
            filename=filename,
            child_size=chunk_size,
            parent_size=parent_size,
            overlap=chunk_overlap,
            semantic_threshold=semantic_threshold,
        )

        text = extract_document_text(
            file_bytes, filename=filename, content_type=content_type
        )
        doc_title = (title or "").strip() or (filename or "未命名文档").rsplit(".", 1)[0]
        row = KbDocument(
            tenant_id=None if is_global else user.tenant_id,
            title=doc_title[:300],
            doc_type=(doc_type or "policy").strip()[:50] or "policy",
            source_file=filename,
            content=text,
            chunk_count=0,
            status="indexing",
            error_message=None,
            version=1,
            uploaded_by=user.id,
            chunk_strategy=cfg.strategy,
            chunk_strategy_effective=cfg.strategy,
            chunk_params=config_to_params(cfg),
        )
        db.add(row)
        await db.flush()
        await index_kb_document(
            db,
            row,
            bump_version=False,
            embed_tenant_id=user.tenant_id,
            config=cfg,
        )
        await db.refresh(row)
        await write_audit_log(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            operation_type="kb.upload",
            target_type="kb",
            target_id=row.id,
            after=_kb_snapshot(row),
        )
        await db.commit()
        return self._serialize(row)

    async def reindex(
        self,
        db: AsyncSession,
        *,
        user: User,
        doc_id: UUID,
        chunk_strategy: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        parent_size: int | None = None,
        semantic_threshold: float | None = None,
    ) -> dict[str, Any]:
        """按请求中的新配置重新切分；未传字段沿用文档原配置。"""
        self._assert_admin(user)
        row = await self.get_document(db, user=user, doc_id=doc_id)
        if not (row.content or "").strip():
            raise BusinessError("文档正文为空，无法索引", code="KB_EMPTY_CONTENT")
        params = row.chunk_params if isinstance(row.chunk_params, dict) else {}
        cfg = normalize_split_config(
            strategy=chunk_strategy or row.chunk_strategy or "parent_child",
            filename=row.source_file,
            child_size=(
                chunk_size
                if chunk_size is not None
                else params.get("child_size")
            ),
            parent_size=(
                parent_size
                if parent_size is not None
                else params.get("parent_size")
            ),
            overlap=(
                chunk_overlap
                if chunk_overlap is not None
                else params.get("overlap")
            ),
            inner_strategy=params.get("inner_strategy"),
            semantic_threshold=(
                semantic_threshold
                if semantic_threshold is not None
                else params.get("semantic_threshold")
            ),
        )
        row.status = "indexing"
        row.error_message = None
        await db.flush()
        await index_kb_document(
            db,
            row,
            bump_version=True,
            embed_tenant_id=user.tenant_id,
            config=cfg,
        )
        await db.refresh(row)
        await write_audit_log(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            operation_type="kb.reindex",
            target_type="kb",
            target_id=row.id,
            after=_kb_snapshot(row),
        )
        await db.commit()
        return self._serialize(row)

    async def delete_document(
        self,
        db: AsyncSession,
        *,
        user: User,
        doc_id: UUID,
    ) -> None:
        """删除文档：先清 Milvus，再删 Postgres（级联 chunks）。"""
        self._assert_admin(user)
        row = await self.get_document(db, user=user, doc_id=doc_id)
        before = _kb_snapshot(row)
        if milvus_kb_store.enabled:
            await asyncio.to_thread(milvus_kb_store.delete_by_doc_id, row.id)
        await db.delete(row)
        await write_audit_log(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            operation_type="kb.delete",
            target_type="kb",
            target_id=doc_id,
            before=before,
        )
        await db.commit()


def _kb_snapshot(row: KbDocument) -> dict[str, Any]:
    """知识库审计快照，不含正文。"""
    return {
        "title": row.title,
        "doc_type": row.doc_type,
        "status": row.status,
        "source_file": row.source_file,
        "chunk_strategy": row.chunk_strategy,
    }


kb_service = KbService()
