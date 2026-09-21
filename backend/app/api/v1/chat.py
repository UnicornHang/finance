"""Chat API：流式对话（SSE）+ 文件上传触发 OCR。

Phase A：增加 multipart 文件上传分支：
1. 上传文件到 MinIO invoices 桶（s3://bucket/key）
2. 计算 SHA-256 hash
3. 调 chat_service.stream_response(..., file_url, file_hash)
4. SSE 返回 sidepanel{status:processing} + text + done
5. Celery worker 异步跑 OCR，结果写库后前端轮询 /invoices/preview/by-hash/{hash} 获取
"""

import hashlib
import json
import logging
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.exceptions import BusinessError
from app.deps import get_current_user
from app.models import User
from app.services.chat_service import chat_service
from app.services.session_service import session_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stream")
async def chat_stream(
    session_id: str | None = Form(default=None),
    message: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式 Agent 回复。

    multipart/form-data：
    - session_id: 可选，空 = 自动创建
    - message: 可选（纯文件上传时可为空）
    - file: 可选，PDF/JPG/PNG/WebP

    SSE 事件：
    - {type: "text", content}       增量文本
    - {type: "sidepanel", payload}  侧弹窗（OCR 上传时为 {type:'invoice', data:{status:'processing',...}}）
    - {type: "done"}                流结束
    - {type: "error", message}      错误
    """
    if not (message or "").strip() and not file:
        raise BusinessError("消息或文件不能同时为空", code="EMPTY_INPUT")

    # 1. 解析 session_id（空则自动创建）
    if not session_id or not session_id.strip():
        new_session = await session_service.create(
            db, user.id, user.tenant_id, title=None
        )
        actual_session_id: UUID = new_session.id
    else:
        try:
            actual_session_id = UUID(session_id)
        except (ValueError, TypeError):
            raise BusinessError("无效的会话 ID", code="INVALID_SESSION_ID")

    # 2. 如果有文件：上传到 MinIO + 计算 hash
    file_url: str | None = None
    file_hash: str | None = None
    if file:
        try:
            content = await file.read()
            if not content:
                raise BusinessError("文件内容为空", code="EMPTY_FILE")

            file_hash = hashlib.sha256(content).hexdigest()
            # 保留原始扩展名以利预览
            ext = Path(file.filename or "invoice.bin").suffix.lower() or ".bin"
            obj_key = f"{user.tenant_id}/{actual_session_id}/{uuid.uuid4()}{ext}"

            file_url = storage_service.upload_file(
                bucket=settings.minio_bucket_invoice,
                object_name=obj_key,
                data=content,
                content_type=file.content_type or "application/octet-stream",
            )
            logger.info(
                "Chat stream: uploaded file tenant=%s session=%s key=%s hash=%s bytes=%d",
                user.tenant_id, actual_session_id, obj_key, file_hash, len(content),
            )
        except BusinessError:
            raise
        except Exception as exc:
            logger.exception("File upload to MinIO failed")
            raise BusinessError(f"文件上传失败：{exc}", code="UPLOAD_FAILED")

    async def event_generator():
        try:
            async for event in chat_service.stream_response(
                db,
                user,
                actual_session_id,
                message or "",
                file_url=file_url,
                file_hash=file_hash,
            ):
                # 首条事件带上 session_id 方便前端确认
                if event.get("type") == "text" and "session_id" not in event:
                    event = {**event, "session_id": str(actual_session_id)}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("chat_stream unexpected error")
            error_event = {"type": "error", "message": f"服务器内部错误：{exc}"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 不缓冲
            "Connection": "keep-alive",
        },
    )


@router.post("/interrupt/{session_id}")
async def interrupt_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
):
    """中断当前 session 的 LLM 流式输出。

    MVP 阶段：仅返回占位响应。完整实现需要：
    1. 用 Redis 维护 session_id → 当前生成任务 ID
    2. 通过 Celery revoke 或 asyncio.Task.cancel 中断
    """
    # TODO: 实现流式中断
    return {"session_id": str(session_id), "interrupted": False, "message": "MVP 占位"}