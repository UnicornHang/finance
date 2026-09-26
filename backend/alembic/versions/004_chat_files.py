"""聊天附件表：文件与会话、消息分开存，识别状态记在附件上

Revision ID: 004
Revises: 003
Create Date: 2026-09-26 09:41:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("original_filename", sa.String(300), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("file_kind", sa.String(20), nullable=False, server_default="file"),
        sa.Column("intent", sa.String(20), nullable=True),
        sa.Column("recognize_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("recognize_error", sa.Text(), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_chat_files_session", "chat_files", ["session_id", "created_at"])
    op.create_index("idx_chat_files_message", "chat_files", ["message_id"])
    # 把已经写在消息 JSON 里的附件搬进独立表，并挂上原来的消息
    op.execute(
        """
        INSERT INTO chat_files (
            tenant_id, user_id, session_id, message_id,
            file_url, file_hash, original_filename, content_type, size, file_kind,
            recognize_status, created_at, updated_at
        )
        SELECT
            m.tenant_id,
            s.user_id,
            m.session_id,
            m.id,
            att->>'file_url',
            att->>'file_hash',
            att->>'original_filename',
            att->>'content_type',
            NULLIF(att->>'size', '')::integer,
            CASE
                WHEN lower(COALESCE(att->>'content_type', '')) LIKE 'image/%'
                  OR lower(COALESCE(att->>'original_filename', '')) ~ '\\.(png|jpe?g|webp|gif|bmp|heic|heif)$'
                THEN 'image'
                ELSE 'file'
            END,
            'succeeded',
            m.created_at,
            m.created_at
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        CROSS JOIN LATERAL jsonb_array_elements(m.attachments) AS att
        WHERE jsonb_typeof(m.attachments) = 'array'
          AND COALESCE(att->>'file_url', '') <> ''
          AND COALESCE(att->>'file_hash', '') <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("idx_chat_files_message", table_name="chat_files")
    op.drop_index("idx_chat_files_session", table_name="chat_files")
    op.drop_table("chat_files")
