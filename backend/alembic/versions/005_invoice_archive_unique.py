"""发票去重只约束已归档记录，待归档允许相同代码和号码

Revision ID: 005
Revises: 004
Create Date: 2026-09-26 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_invoice_tenant_code_number", "invoices", type_="unique")
    op.create_index(
        "uq_invoice_tenant_code_number_active",
        "invoices",
        ["tenant_id", "invoice_code", "invoice_number"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_invoice_tenant_code_number_active", table_name="invoices")
    op.create_unique_constraint(
        "uq_invoice_tenant_code_number",
        "invoices",
        ["tenant_id", "invoice_code", "invoice_number"],
    )
