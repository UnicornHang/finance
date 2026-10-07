"""异步导出任务表 export_jobs

Revision ID: 015
Revises: 014
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 export_jobs 及列表索引、进行中 fingerprint 部分唯一索引。"""
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("artifact_kind", sa.String(10), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(300), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_export_jobs_user_created",
        "export_jobs",
        ["tenant_id", "user_id", "created_at"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uk_export_jobs_inflight_fingerprint
        ON export_jobs (tenant_id, user_id, fingerprint)
        WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    """删除 export_jobs 及相关索引。"""
    op.execute("DROP INDEX IF EXISTS uk_export_jobs_inflight_fingerprint")
    op.drop_index("idx_export_jobs_user_created", table_name="export_jobs")
    op.drop_table("export_jobs")
