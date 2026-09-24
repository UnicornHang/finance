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

from fastapi import APIRouter, Depends, File, UploadFile

from app.config import settings
from app.core.exceptions import BusinessError
from app.deps import get_current_user
from app.models import User
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: Annotated[UploadFile, File(description="任意文件（图片/PDF/Word 等）")],
    user: Annotated[User, Depends(get_current_user)],
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

    logger.info(
        "File upload: tenant=%s user=%s key=%s hash=%s bytes=%d name=%s",
        user.tenant_id, user.id, obj_key, file_hash, len(content), original_filename,
    )

    return {
        "file_hash": file_hash,
        "file_url": file_url,
        "original_filename": original_filename,
        "content_type": content_type,
        "size": len(content),
        "status": "uploaded",
    }
