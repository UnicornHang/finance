"""侧栏「重新识别 / 重新审查」接口测试。

真实写库，模型与 MinIO 下载用 mock，避免依赖外部服务。
"""

from __future__ import annotations

import hashlib
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.services.ocr_service import InvoiceOCRResult


async def _hard_delete_invoices(db_session, tenant_id: UUID) -> None:
    from app.models import Invoice

    await db_session.execute(delete(Invoice).where(Invoice.tenant_id == tenant_id))
    await db_session.commit()


async def _hard_delete_contracts(db_session, tenant_id: UUID) -> None:
    from app.models import Contract

    await db_session.execute(delete(Contract).where(Contract.tenant_id == tenant_id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_invoice_rerecognize_overwrites_fields(client: AsyncClient, auth_headers, db_session):
    """重新识别覆盖字段，保持 pending_review。"""
    payload = {
        "invoice_title": "旧抬头",
        "invoice_code": "011002000111",
        "invoice_number": "88880001",
        "invoice_date": str(date.today()),
        "amount_incl_tax": "10.00",
        "file_url": "s3://invoices/test/rerun.pdf",
        "file_hash": hashlib.sha256(b"rerun-invoice").hexdigest(),
    }
    created = await client.post("/api/v1/invoices/archive", json=payload, headers=auth_headers)
    assert created.status_code == 200, created.text
    inv_id = created.json()["id"]
    tenant_id = None

    mock_result = InvoiceOCRResult(
        invoice_title="新抬头",
        invoice_code="011002000111",
        invoice_number="88880002",
        invoice_date=date.today(),
        amount_incl_tax=99.00,
        invoice_type="electronic",
        seller="新销售方",
        buyer="新购买方",
        confidence={"invoice_number": 0.9},
    )

    async def fake_recognize(_bytes, **_kwargs):
        return mock_result, "llm"

    with (
        patch(
            "app.services.invoice_rerecognize.storage_service.download_bytes",
            return_value=b"%PDF-1.4 mock",
        ),
        patch(
            "app.services.invoice_rerecognize.invoice_vision_service.recognize",
            fake_recognize,
        ),
    ):
        resp = await client.post(f"/api/v1/invoices/{inv_id}/recognize", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == inv_id
    assert body["invoice_title"] == "新抬头"
    assert body["invoice_number"] == "88880002"
    assert float(body["amount_incl_tax"]) == 99.0
    assert body["status"] == "pending_review"

    from app.models import Invoice

    row = await db_session.get(Invoice, UUID(inv_id))
    tenant_id = row.tenant_id
    await _hard_delete_invoices(db_session, tenant_id)


@pytest.mark.asyncio
async def test_invoice_rerecognize_missing_file(client: AsyncClient, auth_headers, db_session):
    """没有原件时应返回业务错误。"""
    payload = {
        "invoice_title": "无原件",
        "invoice_number": "88880003",
        "file_url": "",
        "file_hash": hashlib.sha256(b"no-file").hexdigest(),
    }
    created = await client.post("/api/v1/invoices/archive", json=payload, headers=auth_headers)
    # file_url 为空字符串可能仍写入
    if created.status_code != 200:
        pytest.skip(f"无法创建无原件发票: {created.text}")
    inv_id = created.json()["id"]
    resp = await client.post(f"/api/v1/invoices/{inv_id}/recognize", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVOICE_FILE_MISSING"
    from app.models import Invoice

    row = await db_session.get(Invoice, UUID(inv_id))
    await _hard_delete_invoices(db_session, row.tenant_id)


@pytest.mark.asyncio
async def test_contract_rereview_overwrites_summary(client: AsyncClient, auth_headers, db_session):
    """重新审查覆盖摘要，保持 pending_review。"""
    payload = {
        "contract_name": "旧合同",
        "party_a": "甲方A",
        "party_b": "乙方B",
        "risk_level": "low",
        "review_result": {"summary": "旧摘要", "violations": []},
        "file_url": "s3://contracts/test/rerun.pdf",
        "file_hash": hashlib.sha256(b"rerun-contract").hexdigest(),
    }
    created = await client.post("/api/v1/contracts/archive", json=payload, headers=auth_headers)
    assert created.status_code == 200, created.text
    cid = created.json()["id"]

    with (
        patch(
            "app.services.contract_rereview.storage_service.download_bytes",
            return_value=b"%PDF-1.4 mock",
        ),
        patch(
            "app.services.contract_rereview._prepare_document",
            return_value=([], "甲方：甲公司\n乙方：乙公司\n金额：1000元"),
        ),
        patch(
            "app.services.contract_rereview._extract_contract_overview",
            return_value={"party_a": "甲公司", "party_b": "乙公司", "amount": 1000.0},
        ),
        patch(
            "app.services.contract_rereview._media_content",
            return_value=[{"type": "text", "text": "审查这份合同"}],
        ),
        patch(
            "app.services.contract_rereview._guess_mime",
            return_value="application/pdf",
        ),
        patch(
            "app.services.contract_rereview._rules_block",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "app.services.contract_rereview.llm_service.invoke",
            new=AsyncMock(return_value="## 新审查摘要\n- 条款正常"),
        ),
    ):
        resp = await client.post(f"/api/v1/contracts/{cid}/review", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == cid
    assert body["review_result"]["summary"] == "## 新审查摘要\n- 条款正常"
    assert body["party_a"] == "甲公司"
    assert body["status"] == "pending_review"

    from app.models import Contract

    row = await db_session.get(Contract, UUID(cid))
    await _hard_delete_contracts(db_session, row.tenant_id)
