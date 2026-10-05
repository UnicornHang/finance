"""切分策略：文档与切片增加策略/父子字段

Revision ID: 011
Revises: 010
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """文档记录切分策略；切片记录 role / parent / 是否入向量库。"""
    op.add_column(
        "kb_documents",
        sa.Column("chunk_strategy", sa.String(32), nullable=True),
    )
    op.add_column(
        "kb_documents",
        sa.Column("chunk_strategy_effective", sa.String(32), nullable=True),
    )
    op.add_column(
        "kb_documents",
        sa.Column("chunk_params", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "kb_chunks",
        sa.Column("role", sa.String(16), nullable=False, server_default="leaf"),
    )
    op.add_column(
        "kb_chunks",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "kb_chunks",
        sa.Column("section_path", sa.String(500), nullable=True),
    )
    op.add_column(
        "kb_chunks",
        sa.Column(
            "embeddable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index("idx_kb_chunks_parent", "kb_chunks", ["parent_id"])
    op.create_index("idx_kb_chunks_role", "kb_chunks", ["doc_id", "role"])


def downgrade() -> None:
    """回滚切分策略字段。"""
    op.drop_index("idx_kb_chunks_role", table_name="kb_chunks")
    op.drop_index("idx_kb_chunks_parent", table_name="kb_chunks")
    op.drop_column("kb_chunks", "embeddable")
    op.drop_column("kb_chunks", "section_path")
    op.drop_column("kb_chunks", "parent_id")
    op.drop_column("kb_chunks", "role")
    op.drop_column("kb_documents", "chunk_params")
    op.drop_column("kb_documents", "chunk_strategy_effective")
    op.drop_column("kb_documents", "chunk_strategy")
