"""messages.attachments：图片和文件跟文字写在同一条消息上

Revision ID: 003
Revises: 002
Create Date: 2026-09-26 08:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # 旧记录把附件塞在 tool_calls.attachments，搬到独立字段，并和文字留在同一行
    op.execute(
        """
        UPDATE messages
        SET attachments = tool_calls->'attachments'
        WHERE tool_calls ? 'attachments'
          AND jsonb_typeof(tool_calls->'attachments') = 'array'
        """
    )
    op.execute(
        """
        UPDATE messages
        SET tool_calls = NULLIF(tool_calls - 'attachments', '{}'::jsonb)
        WHERE tool_calls ? 'attachments'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE messages
        SET tool_calls = COALESCE(tool_calls, '{}'::jsonb) || jsonb_build_object('attachments', attachments)
        WHERE attachments IS NOT NULL
        """
    )
    op.drop_column("messages", "attachments")
