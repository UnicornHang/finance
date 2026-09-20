"""Chat API：流式对话（SSE）。"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessError
from app.deps import get_current_user
from app.models import User
from app.services.chat_service import chat_service
from app.services.session_service import session_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stream")
async def chat_stream(
    session_id: str | None = Form(default=None),
    message: str = Form(...),
    file: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式 Agent 回复。

    流程：
    1. 校验或自动创建会话
    2. 持久化用户消息
    3. 加载上下文历史
    4. 流式调用 LLM
    5. 持久化助手消息

    SSE 事件：
    - {type: "text", content}    增量文本
    - {type: "sidepanel", ...}   触发侧弹窗（未来：OCR/合同结果）
    - {type: "done"}            流结束
    - {type: "error", message}   错误
    """
    if not message or not message.strip():
        raise BusinessError("消息内容不能为空", code="EMPTY_MESSAGE")

    # 1. 解析 session_id（空则自动创建）
    if not session_id or session_id.strip() == "":
        new_session = await session_service.create(
            db, user.id, user.tenant_id, title=None
        )
        actual_session_id: UUID = new_session.id
    else:
        try:
            actual_session_id = UUID(session_id)
        except (ValueError, TypeError):
            raise BusinessError("无效的会话 ID", code="INVALID_SESSION_ID")

    # 文件上传暂未接入（Phase 2）
    if file:
        logger.info("chat_stream received file: %s (will be wired in Phase 2)", file.filename)

    async def event_generator():
        try:
            async for event in chat_service.stream_response(
                db, user, actual_session_id, message
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