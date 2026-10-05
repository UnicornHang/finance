"""kb_chunks 增加稀疏检索词与 GIN 全文索引

Revision ID: 010
Revises: 009
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为混合检索写入分词列，并用 generated tsvector 建 GIN。"""
    op.add_column("kb_chunks", sa.Column("search_tokens", sa.Text(), nullable=True))
    op.execute(
        """
        ALTER TABLE kb_chunks
        ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(search_tokens, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX idx_kb_chunks_search_tsv ON kb_chunks USING GIN (search_tsv)"
    )


def downgrade() -> None:
    """移除稀疏检索列与索引。"""
    op.execute("DROP INDEX IF EXISTS idx_kb_chunks_search_tsv")
    op.execute("ALTER TABLE kb_chunks DROP COLUMN IF EXISTS search_tsv")
    op.drop_column("kb_chunks", "search_tokens")
