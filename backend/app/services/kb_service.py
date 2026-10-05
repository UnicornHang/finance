"""知识库文档服务：上传解析、切分向量化、列表/删除/重索引。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.services.invoice_document import _extract_file_text, _guess_mime
from app.services.milvus_service import milvus_kb_store
from app.services.rag_service import rag_service
from app.services.rag_tokenize import to_search_tokens

if TYPE_CHECKING:
    from app.models import KbDocument, User

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf", ".docx", ".doc"}


def recursive_split(
    content: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """按段落优先切分，控制块长与重叠。"""
    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    parts = re.split(r"\n\s*\n", text)
    if len(parts) == 1:
        parts = text.split("\n")
    if len(parts) == 1:
        parts = re.split(r"(?<=[。！？；.!?])\s*", text)

    chunks: list[str] = []
    buf = ""
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        candidate = f"{buf}\n{piece}".strip() if buf else piece
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        if len(piece) <= chunk_size:
            buf = piece
            continue
        start = 0
        while start < len(piece):
            end = min(start + chunk_size, len(piece))
            chunks.append(piece[start:end])
            if end >= len(piece):
                break
            start = max(end - overlap, start + 1)
        buf = ""
    if buf:
        chunks.append(buf)
    return chunks


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

    def _assert_admin(self, user: "User") -> None:
        if user.role != "admin":
            raise ForbiddenError("仅管理员可管理知识库", code="KB_FORBIDDEN")

    def _serialize(self, row: "KbDocument") -> dict[str, Any]:
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
        from app.models import KbChunk

        row = await self.get_document(db, user=user, doc_id=doc_id)
        result = await db.execute(
            select(KbChunk)
            .where(KbChunk.doc_id == row.id)
            .order_by(KbChunk.chunk_index.asc())
            .limit(200)
        )
        chunks = [
            {
                "id": str(c.id),
                "chunk_index": c.chunk_index,
                "content": c.content,
                "token_count": c.token_count,
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
        from app.models import KbDocument

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
    ) -> "KbDocument":
        """读取单份文档并校验可见性。"""
        from app.models import KbDocument

        row = await db.get(KbDocument, doc_id)
        if row is None:
            raise NotFoundError("文档不存在", code="KB_NOT_FOUND")
        if row.tenant_id is not None and row.tenant_id != user.tenant_id:
            raise ForbiddenError("无权访问该文档", code="KB_FORBIDDEN")
        return row

    def get_index_settings(self) -> dict[str, Any]:
        """返回上传弹窗用的默认索引参数。"""
        return {
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
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
        user: "User",
        file_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        title: str | None = None,
        doc_type: str | None = None,
        is_global: bool = False,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ) -> dict[str, Any]:
        """上传并同步完成切分向量化。"""
        self._assert_admin(user)
        from app.models import KbDocument

        size = int(chunk_size) if chunk_size else CHUNK_SIZE
        overlap = int(chunk_overlap) if chunk_overlap else CHUNK_OVERLAP
        if size < 100 or size > 4000:
            raise BusinessError("分段长度须在 100–4000 之间", code="KB_CHUNK_SIZE_INVALID")
        if overlap < 0 or overlap >= size:
            raise BusinessError("重叠长度须 ≥0 且小于分段长度", code="KB_CHUNK_OVERLAP_INVALID")

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
        )
        db.add(row)
        await db.flush()
        try:
            await self._index_document(
                db,
                row,
                bump_version=False,
                embed_tenant_id=user.tenant_id,
                chunk_size=size,
                chunk_overlap=overlap,
            )
        except BusinessError:
            # 保留 failed 记录，便于前端看到错误后点重索引
            await db.commit()
            await db.refresh(row)
            return self._serialize(row)
        await db.commit()
        await db.refresh(row)
        return self._serialize(row)

    async def reindex(
        self,
        db: AsyncSession,
        *,
        user: "User",
        doc_id: UUID,
    ) -> dict[str, Any]:
        """重新切分并向量化；失败也会落库 failed 状态。"""
        self._assert_admin(user)
        row = await self.get_document(db, user=user, doc_id=doc_id)
        if not (row.content or "").strip():
            raise BusinessError("文档正文为空，无法索引", code="KB_EMPTY_CONTENT")
        row.status = "indexing"
        row.error_message = None
        await db.flush()
        try:
            await self._index_document(
                db, row, bump_version=True, embed_tenant_id=user.tenant_id
            )
        except BusinessError:
            await db.commit()
            await db.refresh(row)
            return self._serialize(row)
        await db.commit()
        await db.refresh(row)
        return self._serialize(row)

    async def delete_document(
        self,
        db: AsyncSession,
        *,
        user: "User",
        doc_id: UUID,
    ) -> None:
        """删除文档：先清 Milvus，再删 Postgres（级联 chunks）。"""
        self._assert_admin(user)
        row = await self.get_document(db, user=user, doc_id=doc_id)
        if milvus_kb_store.enabled:
            await asyncio.to_thread(milvus_kb_store.delete_by_doc_id, row.id)
        await db.delete(row)
        await db.commit()

    async def _index_document(
        self,
        db: AsyncSession,
        row: "KbDocument",
        *,
        bump_version: bool,
        embed_tenant_id: UUID,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ) -> None:
        """切分 → Embedding → Postgres 正文/稀疏词 → Milvus 向量。"""
        from app.models import KbChunk

        try:
            chunks = recursive_split(
                row.content or "", chunk_size=chunk_size, overlap=chunk_overlap
            )
            if not chunks:
                raise BusinessError("切分结果为空", code="KB_EMPTY_CONTENT")

            # 先清旧向量与旧块
            if milvus_kb_store.enabled:
                await asyncio.to_thread(milvus_kb_store.delete_by_doc_id, row.id)
            await db.execute(delete(KbChunk).where(KbChunk.doc_id == row.id))

            # 通用文档 tenant_id 为空，Embedding 密钥仍按操作者租户解析
            embeddings = await rag_service.embed_batch(
                chunks, db=db, tenant_id=embed_tenant_id
            )
            if len(embeddings) != len(chunks):
                raise BusinessError("向量化结果数量不匹配", code="KB_EMBED_MISMATCH")

            chunk_rows: list[KbChunk] = []
            for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                # 企业主路径向量在 Milvus；PG embedding 可空，仅作降级备份可选写入
                chunk = KbChunk(
                    doc_id=row.id,
                    tenant_id=row.tenant_id,
                    chunk_index=idx,
                    content=chunk_text,
                    search_tokens=to_search_tokens(chunk_text, title=row.title),
                    embedding=emb if settings.kb_store_pg_embedding else None,
                    token_count=len(chunk_text),
                    metadata_={"title": row.title, "doc_type": row.doc_type},
                )
                db.add(chunk)
                chunk_rows.append(chunk)
            await db.flush()
            milvus_rows = [
                {
                    "chunk_id": chunk.id,
                    "doc_id": row.id,
                    "tenant_id": row.tenant_id,
                    "doc_type": row.doc_type or "policy",
                    "embedding": emb,
                }
                for chunk, emb in zip(chunk_rows, embeddings)
            ]

            if milvus_kb_store.enabled:
                await asyncio.to_thread(milvus_kb_store.upsert_chunks, milvus_rows)
            elif not settings.kb_store_pg_embedding:
                raise BusinessError(
                    "Milvus 未启用且未开启 PG 向量备份，无法完成索引",
                    code="KB_VECTOR_STORE_REQUIRED",
                )

            row.chunk_count = len(chunks)
            row.embedding_model = settings.embedding_model
            row.status = "active"
            row.error_message = None
            if bump_version:
                row.version = (row.version or 1) + 1
            await db.flush()
            logger.info(
                "kb indexed id=%s chunks=%s milvus=%s",
                row.id,
                len(chunks),
                milvus_kb_store.enabled,
            )
        except Exception as exc:
            logger.exception("kb index failed id=%s", row.id)
            row.status = "failed"
            row.error_message = str(exc)[:1000]
            row.chunk_count = 0
            await db.flush()
            if isinstance(exc, BusinessError):
                raise
            raise BusinessError(f"向量化失败：{exc}", code="KB_INDEX_FAILED") from exc


kb_service = KbService()
