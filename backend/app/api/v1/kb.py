"""知识库管理 API。

- GET  /kb/documents              列表
- POST /kb/documents              上传并索引
- DELETE /kb/documents/{doc_id}   删除
- POST /kb/documents/{doc_id}/reindex  重新向量化
- POST /kb/test-retrieve          检索测试
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessError, ForbiddenError
from app.deps import get_current_user
from app.models import User
from app.services.kb_service import kb_service
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)
router = APIRouter()


class TestRetrieveRequest(BaseModel):
    """检索测试请求。"""

    question: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    doc_type: str | None = None


@router.get("/documents")
async def list_documents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """文档列表（租户 + 通用）。"""
    return await kb_service.list_documents(db, user=user)


@router.post("/documents")
async def upload_document(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(description="制度/规则文档")],
    title: Annotated[str | None, Form()] = None,
    doc_type: Annotated[str | None, Form()] = None,
    is_global: Annotated[bool, Form()] = False,
):
    """上传知识库文档并同步切分向量化。"""
    raw = await file.read()
    if not raw:
        raise BusinessError("空文件", code="KB_EMPTY_FILE")
    return await kb_service.upload_document(
        db,
        user=user,
        file_bytes=raw,
        filename=file.filename,
        content_type=file.content_type,
        title=title,
        doc_type=doc_type,
        is_global=is_global,
    )


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除文档。"""
    await kb_service.delete_document(db, user=user, doc_id=doc_id)
    return {"ok": True, "id": str(doc_id)}


@router.post("/documents/{doc_id}/reindex")
async def reindex_document(
    doc_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """重新向量化（种子文档首次索引也走这里）。"""
    return await kb_service.reindex(db, user=user, doc_id=doc_id)


@router.post("/test-retrieve")
async def test_retrieve(
    body: TestRetrieveRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """检索测试：返回召回片段。"""
    if user.role != "admin":
        raise ForbiddenError("仅管理员可测试检索", code="KB_FORBIDDEN")
    hits = await rag_service.retrieve(
        db,
        body.question,
        str(user.tenant_id),
        top_k=body.top_k,
        doc_type=body.doc_type,
    )
    return {
        "question": body.question,
        "total": len(hits),
        "items": hits,
    }
