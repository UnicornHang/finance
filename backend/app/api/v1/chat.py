"""Chat API：流式 Agent 回复（SSE）。

调用模型：客户端先 `POST /api/v1/files/upload` 把文件落到 MinIO，
拿到 `{file_hash, file_url}` 后带这两个值进 `POST /api/v1/chat/stream`。

文件决定权交给 chat_service / LLM：根据 user_message 语义判断是 ocr_invoice /
parse_document / kb_query，agent 内部选择下一步动作。
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessError
from app.deps import get_current_user
from app.models import User
from app.services.chat_service import chat_service
from app.services.session_service import session_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatStreamRequest(BaseModel):
    """SSE 流式 Agent 请求体（JSON）。"""

    session_id: str | None = None
    message: str = ""
    file_url: str | None = None
    file_hash: str | None = None
    file_meta: dict | None = None  # {original_filename, content_type, size}


@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式 Agent 回复（JSON 请求体）。

    请求字段：
    - session_id: 可选（空 = 自动新建会话）
    - message: 用户文本（可选，但与 file_url 至少要有一个）
    - file_url / file_hash: 由 `POST /files/upload` 预先产出
    - file_meta: 可选，原始文件名 / content_type / size

    SSE 事件：
    - {type: "text", content}             增量文本（模型流式返回 / 思考中间步骤）
    - {type: "sidepanel", payload}        结构化数据 ready 时右侧持久栏触发
    - {type: "done"}                      流结束
    - {type: "error", message}            错误
    """
    if not (body.message or "").strip() and not body.file_url:
        raise BusinessError("消息或文件不能同时为空", code="EMPTY_INPUT")

    # 1. 解析 session_id（空则自动创建）
    if not body.session_id or not body.session_id.strip():
        new_session = await session_service.create(
            db, user.id, user.tenant_id, title=None
        )
        actual_session_id: UUID = new_session.id
    else:
        try:
            actual_session_id = UUID(body.session_id)
        except (ValueError, TypeError):
            raise BusinessError("无效的会话 ID", code="INVALID_SESSION_ID")

    # 2. 文件已在 /files/upload 阶段落到 MinIO；这里只携带引用
    file_url = body.file_url
    file_hash = body.file_hash

    async def event_generator():
        try:
            async for event in chat_service.stream_response(
                db,
                user,
                actual_session_id,
                body.message or "",
                file_url=file_url,
                file_hash=file_hash,
                file_meta=body.file_meta,
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
