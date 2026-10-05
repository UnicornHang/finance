"""users 表增加登录失败计数与锁定截止时间

Revision ID: 009
Revises: 008
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为登录锁定增加 failed_login_attempts、locked_until。"""
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """移除登录锁定字段。"""
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
