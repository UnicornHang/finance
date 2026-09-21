"""invoice dedup + llm system_prompt

Revision ID: 002
Revises: 001
Create Date: 2026-09-21 22:00:00.000000

Phase A:
- invoices: 加唯一约束 (tenant_id, invoice_code, invoice_number) 阻断重复归档
- llm_configs: 加 system_prompt Text 列供 LLM 设置 UI 持久化
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 发票去重唯一约束
    # 注：当前 seed.py 不写 invoices，理论上无重复；若生产已有数据，
    # 可先用以下 SQL 查重再决定：SELECT invoice_code, invoice_number, count(*) FROM invoices GROUP BY 1,2 HAVING count(*) > 1
    op.create_unique_constraint(
        "uq_invoice_tenant_code_number",
        "invoices",
        ["tenant_id", "invoice_code", "invoice_number"],
    )

    # 2. LLM 配置 system_prompt 列
    op.add_column(
        "llm_configs",
        sa.Column("system_prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_configs", "system_prompt")
    op.drop_constraint("uq_invoice_tenant_code_number", "invoices", type_="unique")