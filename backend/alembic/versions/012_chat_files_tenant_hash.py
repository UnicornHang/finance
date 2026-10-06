"""聊天附件按租户+hash 查找，上传去重用。

Revision ID: 012
Revises: 011
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_chat_files_tenant_hash",
        "chat_files",
        ["tenant_id", "file_hash"],
    )


def downgrade() -> None:
    op.drop_index("idx_chat_files_tenant_hash", table_name="chat_files")
