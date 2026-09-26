"""聊天附件：上传成功后落库，发送时绑定消息，识别状态记在本行。"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ForbiddenError
from app.models import ChatFile, User


def _file_kind(content_type: str | None, filename: str | None) -> str:
    """图片记 image，其余文档、压缩包等都记 file。"""
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    name = (filename or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif")):
        return "image"
    return "file"


class ChatFileService:
    """chat_files 的创建、绑定和状态更新。任何上传成功的图片或文件都写一行。"""

    async def create_uploaded(
        self,
        db: AsyncSession,
        user: User,
        session_id: UUID,
        *,
        file_url: str,
        file_hash: str,
        original_filename: str | None,
        content_type: str | None,
        size: int | None,
    ) -> ChatFile:
        """MinIO 已写入后插入一行。此时还没有消息，识别状态为待识别。"""
        row = ChatFile(
            tenant_id=user.tenant_id,
            user_id=user.id,
            session_id=session_id,
            file_url=file_url,
            file_hash=file_hash,
            original_filename=original_filename,
            content_type=content_type,
            size=size,
            file_kind=_file_kind(content_type, original_filename),
            recognize_status="pending",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def resolve_for_send(
        self,
        db: AsyncSession,
        user: User,
        session_id: UUID,
        *,
        file_id: UUID | None,
        file_url: str | None,
        file_hash: str | None,
        file_meta: dict | None,
    ) -> ChatFile | None:
        """发送时拿到附件行。有 file_id 就校验归属；只有 url 时补建一行，兼容旧客户端。"""
        if file_id is not None:
            row = await db.get(ChatFile, file_id)
            if row is None or row.tenant_id != user.tenant_id:
                raise BusinessError("附件不存在", code="FILE_NOT_FOUND")
            if row.user_id != user.id or row.session_id != session_id:
                raise ForbiddenError("无权使用该附件", code="FILE_FORBIDDEN")
            return row
        if not file_url or not file_hash:
            return None
        meta = file_meta or {}
        size = meta.get("size")
        return await self.create_uploaded(
            db,
            user,
            session_id,
            file_url=file_url,
            file_hash=file_hash,
            original_filename=meta.get("original_filename"),
            content_type=meta.get("content_type"),
            size=size if isinstance(size, int) else None,
        )

    async def bind_message(self, db: AsyncSession, row: ChatFile, message_id: UUID) -> None:
        """把附件挂到刚保存的那条用户消息上。"""
        row.message_id = message_id
        await db.commit()

    async def mark(self, db: AsyncSession, file_id: UUID, **fields: Any) -> None:
        """更新意图、识别状态、错误或业务单据 ID，并立即提交。"""
        row = await db.get(ChatFile, file_id)
        if row is None:
            return
        for key, value in fields.items():
            setattr(row, key, value)
        await db.commit()

    async def list_by_message_ids(
        self, db: AsyncSession, message_ids: list[UUID]
    ) -> dict[UUID, list[ChatFile]]:
        """按消息批量取出附件，供历史列表和模型上下文使用。"""
        if not message_ids:
            return {}
        result = await db.execute(
            select(ChatFile)
            .where(ChatFile.message_id.in_(message_ids))
            .order_by(ChatFile.created_at.asc())
        )
        grouped: dict[UUID, list[ChatFile]] = {}
        for row in result.scalars().all():
            if row.message_id is None:
                continue
            grouped.setdefault(row.message_id, []).append(row)
        return grouped

    def to_attachment(self, row: ChatFile) -> dict[str, Any]:
        """消息接口里的附件结构，字段与气泡展示一致。"""
        return {
            "id": str(row.id),
            "file_url": row.file_url,
            "file_hash": row.file_hash,
            "original_filename": row.original_filename,
            "content_type": row.content_type,
            "size": row.size,
            "file_kind": row.file_kind,
            "intent": row.intent,
            "recognize_status": row.recognize_status,
            "recognize_error": row.recognize_error,
        }

    def prompt_hint(self, rows: list[ChatFile]) -> str:
        """拼进后续对话的附件摘要，让模型知道这句话挂了哪个文件。"""
        lines: list[str] = []
        for row in rows:
            name = row.original_filename or "附件"
            intent = row.intent or "unknown"
            lines.append(f"[附件] {name} intent={intent} recognize={row.recognize_status}")
        return "\n".join(lines)


chat_file_service = ChatFileService()
