"""历史消息向量：按段保存并绑定租户

Revision ID: 014
Revises: 013
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """清空无写入路径的旧行，增加租户、分段索引与原文列及唯一约束。"""
    # 表尚无写入路径，旧行无 tenant/content，必须先清空再设 NOT NULL
    op.execute("DELETE FROM message_embeddings")

    op.add_column(
        "message_embeddings",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.add_column(
        "message_embeddings",
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "message_embeddings",
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_message_embeddings_message_chunk",
        "message_embeddings",
        ["message_id", "chunk_index"],
    )


def downgrade() -> None:
    """先删唯一约束，再移除三列。"""
    op.drop_constraint(
        "uq_message_embeddings_message_chunk",
        "message_embeddings",
        type_="unique",
    )
    op.drop_column("message_embeddings", "content")
    op.drop_column("message_embeddings", "chunk_index")
    op.drop_column("message_embeddings", "tenant_id")
