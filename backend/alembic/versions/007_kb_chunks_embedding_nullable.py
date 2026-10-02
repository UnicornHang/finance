"""kb_chunks.embedding 可空：向量主存 Milvus

Revision ID: 007
Revises: 006
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """向量改由 Milvus 承载，Postgres 列允许为空。"""
    op.alter_column(
        "kb_chunks",
        "embedding",
        existing_type=Vector(1536),
        nullable=True,
    )


def downgrade() -> None:
    """回退为非空（需先回填向量，否则可能失败）。"""
    op.alter_column(
        "kb_chunks",
        "embedding",
        existing_type=Vector(1536),
        nullable=False,
    )
