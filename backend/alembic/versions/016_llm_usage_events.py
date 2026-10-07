"""LLM 用量事件表 + sessions token 汇总列

Revision ID: 016
Revises: 015
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scene", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_missing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(20), nullable=False, server_default="complete"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_llm_usage_tenant_created", "llm_usage_events", ["tenant_id", "created_at"])
    op.create_index("idx_llm_usage_tenant_session", "llm_usage_events", ["tenant_id", "session_id"])

    op.add_column("sessions", sa.Column("prompt_tokens_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sessions", sa.Column("completion_tokens_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sessions", sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("sessions", "total_tokens")
    op.drop_column("sessions", "completion_tokens_total")
    op.drop_column("sessions", "prompt_tokens_total")
    op.drop_index("idx_llm_usage_tenant_session", table_name="llm_usage_events")
    op.drop_index("idx_llm_usage_tenant_created", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")
