"""聊天附件增加 extract_result，保存合同侧栏字段

Revision ID: 006
Revises: 005
Create Date: 2026-10-01 20:15:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """合同审查抽出的甲方/乙方等，重开会话时侧栏要还能读到。"""
    op.add_column(
        "chat_files",
        sa.Column("extract_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_files", "extract_result")
