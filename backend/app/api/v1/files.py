"""通用文件上传 API。

本路由**只负责把用户文件落到 MinIO**，不做任何业务判断（不触发 OCR /
合同审查 / RAG）。`POST /chat/stream` 拿到上传后的 `file_url` + `file_hash`
后由 chat_service 决定下一步动作。
"""

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.exceptions import BusinessError, ForbiddenError
from app.deps import get_current_user
from app.models import User
from app.services.chat_file_service import chat_file_service
from app.services.session_service import session_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    """s3://bucket/key → (bucket, key)。"""
    if not s3_url.startswith("s3://"):
        raise BusinessError("无效的文件地址", code="INVALID_FILE_URL")
    rest = s3_url[len("s3://") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise BusinessError("无效的文件地址", code="INVALID_FILE_URL")
    return bucket, unquote(key)


@router.post("/upload")
async def upload_file(
    file: Annotated[UploadFile, File(description="任意文件（图片/PDF/Word 等）")],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: Annotated[str, Form(description="当前会话 ID，附件先挂会话，发送后再挂消息")],
) -> dict[str, Any]:
    """通用 multipart 文件上传 → MinIO。

    行为：
    1. 读取 multipart → SHA-256
    2. 上传到 `settings.minio_bucket_kb`（通用桶；OCR/合同任务自己下载再分发）
    3. 返回 `{file_hash, file_url, original_filename, content_type, size}`

    前端拿到 `file_url` + `file_hash` 后把它们作为 JSON 字段随消息一起
    发到 `POST /api/v1/chat/stream`，由 chat_service 决定后续动作。
    """
    try:
        actual_session_id = UUID(session_id)
    except (ValueError, TypeError):
        raise BusinessError("无效的会话 ID", code="INVALID_SESSION_ID")
    await session_service.verify_access(db, actual_session_id, user.id, user.tenant_id)

    try:
        content = await file.read()
    except Exception as exc:
        logger.exception("Failed to read uploaded file")
        raise BusinessError(f"读取文件失败：{exc}", code="UPLOAD_READ_FAILED")
    if not content:
        raise BusinessError("文件内容为空", code="EMPTY_FILE")

    file_hash = hashlib.sha256(content).hexdigest()
    original_filename = file.filename or "upload.bin"
    ext = Path(original_filename).suffix.lower() or ".bin"
    content_type = file.content_type or "application/octet-stream"

    # 把所有上传暂存到通用 `files/` 桶；chat_stream 拿到 URL 后续任务
    # 自行决定分流到 OCR / 合同解析 / RAG。
    obj_key = f"{user.tenant_id}/files/{uuid.uuid4()}{ext}"

    try:
        file_url = storage_service.upload_file(
            bucket=settings.minio_bucket_kb,
            object_name=obj_key,
            data=content,
            content_type=content_type,
        )
    except Exception as exc:
        logger.exception("MinIO upload failed")
        raise BusinessError(f"文件上传失败：{exc}", code="UPLOAD_FAILED")

    row = await chat_file_service.create_uploaded(
        db,
        user,
        actual_session_id,
        file_url=file_url,
        file_hash=file_hash,
        original_filename=original_filename,
        content_type=content_type,
        size=len(content),
    )

    logger.info(
        "File upload: tenant=%s user=%s key=%s hash=%s bytes=%d name=%s file_id=%s",
        user.tenant_id, user.id, obj_key, file_hash, len(content), original_filename, row.id,
    )

    return {
        "id": str(row.id),
        "file_hash": file_hash,
        "file_url": file_url,
        "original_filename": original_filename,
        "content_type": content_type,
        "size": len(content),
        "recognize_status": row.recognize_status,
        "status": "uploaded",
    }


@router.get("/presign")
async def presign_file(
    user: Annotated[User, Depends(get_current_user)],
    file_url: Annotated[str, Query(description="s3://bucket/key 形式的对象地址")],
    expires: Annotated[int, Query(ge=60, le=86400)] = 3600,
) -> dict[str, Any]:
    """为已上传文件生成临时预览/下载 URL（仅允许访问本租户路径下的对象）。"""
    bucket, key = _parse_s3_url(file_url)
    tenant_prefix = f"{user.tenant_id}/"
    if not key.startswith(tenant_prefix):
        raise ForbiddenError("无权访问该文件", code="FILE_FORBIDDEN")

    allowed_buckets = {
        settings.minio_bucket_kb,
        settings.minio_bucket_invoice,
        settings.minio_bucket_contract,
    }
    if bucket not in allowed_buckets:
        raise ForbiddenError("无权访问该文件", code="FILE_FORBIDDEN")

    try:
        url = storage_service.get_presigned_url(bucket, key, expires=expires)
    except Exception as exc:
        logger.exception("presign failed: %s", file_url)
        raise BusinessError(f"生成预览链接失败：{exc}", code="PRESIGN_FAILED") from exc

    return {"url": url, "expires_in": expires}
