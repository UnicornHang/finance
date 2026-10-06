"""会话摘要：记录已覆盖到的最后一条消息游标

Revision ID: 013
Revises: 012
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加可空游标列，指向摘要已覆盖的最后一条消息。"""
    op.add_column(
        "sessions",
        sa.Column("summary_until_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_summary_until_message",
        "sessions",
        "messages",
        ["summary_until_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """先移除外键，再删除游标列。"""
    op.drop_constraint("fk_sessions_summary_until_message", "sessions", type_="foreignkey")
    op.drop_column("sessions", "summary_until_message_id")
