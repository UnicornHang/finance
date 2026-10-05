"""数据概览 API 测试。"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.models import AuditLog, Invoice
from app.services.dashboard_service import _shanghai_day_key, delta_pct, shift_month


def test_delta_pct_and_shift_month():
    """环比与月份换算。"""
    assert delta_pct(12, 10) == 20.0
    assert delta_pct(8, 10) == -20.0
    assert delta_pct(5, 0) is None
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)


def test_shanghai_day_key_normalizes_datetime():
    """UTC 深夜应落到上海次日，且格式为 YYYY-MM-DD。"""
    ts = datetime(2026, 10, 5, 16, 30, tzinfo=timezone.utc)
    assert _shanghai_day_key(ts) == "2026-10-06"
    naive = datetime(2026, 10, 5, 2, 0, 0)
    assert _shanghai_day_key(naive) == "2026-10-05"


@pytest.mark.asyncio
async def test_overview_forbidden_for_employee(client: AsyncClient, employee_headers):
    """员工不能看数据概览。"""
    r = await client.get("/api/v1/dashboard/overview", headers=employee_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_overview_ok_for_finance(client: AsyncClient, finance_headers):
    """财务可读取看板结构。"""
    r = await client.get("/api/v1/dashboard/overview?days=7", headers=finance_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["days"] == 7
    assert "today_archived" in body["kpis"]
    assert len(body["trend"]["points"]) == 7


@pytest.mark.asyncio
async def test_overview_counts_confirmed_invoice(client: AsyncClient, auth_headers, db_session):
    """确认归档后，今日归档与本月金额上升。"""
    before = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert before.status_code == 200, before.text
    before_today = before.json()["kpis"]["today_archived"]["value"]
    before_amount = before.json()["kpis"]["month_invoice_amount"]["value"]

    number = f"9{uuid4().hex[:7]}"
    payload = {
        "invoice_title": "看板测试发票",
        "company": "测试公司",
        "invoice_code": "011002000111",
        "invoice_number": number,
        "invoice_date": str(date.today()),
        "amount_excl_tax": "1000.00",
        "tax_amount": "130.00",
        "amount_incl_tax": "1130.00",
        "invoice_type": "special",
        "file_url": "s3://invoices/test/dashboard.pdf",
        "file_hash": hashlib.sha256(uuid4().bytes).hexdigest(),
    }
    created = await client.post("/api/v1/invoices/archive", json=payload, headers=auth_headers)
    assert created.status_code == 200, created.text
    inv_id = created.json()["id"]
    confirmed = await client.post(
        f"/api/v1/invoices/{inv_id}/confirm",
        json={},
        headers=auth_headers,
    )
    assert confirmed.status_code == 200, confirmed.text

    after = await client.get("/api/v1/dashboard/overview?days=30", headers=auth_headers)
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["days"] == 30
    assert len(body["trend"]["points"]) == 30
    assert body["kpis"]["today_archived"]["value"] >= before_today + 1
    assert body["kpis"]["month_invoice_amount"]["value"] >= before_amount + 1130
    assert any(item["id"] == inv_id for item in body["recent_archives"])

    await db_session.execute(delete(AuditLog).where(AuditLog.target_id == UUID(inv_id)))
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()
