"""发票归档 API 集成测试（Phase A）。

覆盖：
- 列表 / 详情 / 编辑 / 软删 / 确认
- 去重（409）
- 行级权限（员工仅看自己）
- 审计日志写入
- 文件预签名 URL
- /preview/by-hash 轮询

所有测试在真实 Postgres 上跑（连 .env 配置的 DB），每个测试结束清理该用户创建的发票，
避免污染其他测试。
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

# ===================================================================
# 测试夹具：每个用例前后清理
# ===================================================================


@pytest.fixture
async def cleanup_invoices(db_session):
    """用例结束删除测试中创建的所有发票（按 tenant 隔离）。"""
    yield
    # 这里不做硬清理，而是依赖 status='deleted' 软删隔离
    # 如果测试用例想验证硬删除，可以手动调用


async def _archive(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    code: str = "011002000111",
    number: str = "12345678",
    title: str = "测试发票",
    amount: str = "1130.00",
    file_hash: str | None = None,
) -> dict[str, Any]:
    """调用 POST /invoices/archive，返回响应体。"""
    payload = {
        "invoice_title": title,
        "company": "测试公司有限公司",
        "tax_id": "91110000XXXXXXXXXX",
        "invoice_code": code,
        "invoice_number": number,
        "invoice_date": str(date.today()),
        "amount_excl_tax": "1000.00",
        "tax_amount": "130.00",
        "amount_incl_tax": amount,
        "invoice_type": "electronic",
        "seller": "销售方A",
        "buyer": "购买方B",
        "file_url": "s3://invoices/test/sample.pdf",
        "file_hash": file_hash or hashlib.sha256(uuid4().bytes).hexdigest(),
    }
    r = await client.post("/api/v1/invoices/archive", json=payload, headers=headers)
    return {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}


async def _hard_delete_invoices(db_session, tenant_id: UUID) -> None:
    """清理某个租户的所有发票（仅供测试）。"""
    from app.models import Invoice

    await db_session.execute(
        delete(Invoice).where(Invoice.tenant_id == tenant_id)
    )
    await db_session.commit()


# ===================================================================
# 用例 1：列表空 → 创建一条 → 列表 1 条
# ===================================================================


@pytest.mark.asyncio
async def test_archive_create_and_list(client, auth_headers, db_session, cleanup_invoices):
    # 拿当前用户的 tenant_id（从 list 第一个响应的 user 反查太麻烦，直接走清理）
    r = await _archive(client, auth_headers, number="10000001", file_hash=hashlib.sha256(b"n1").hexdigest())
    assert r["status"] == 200, r["body"]
    inv = r["body"]
    assert inv["status"] == "pending_review"
    assert inv["invoice_code"] == "011002000111"
    assert inv["invoice_number"] == "10000001"

    # 列表（默认 status_filter=active，应过滤掉 pending_review）
    r2 = await client.get("/api/v1/invoices/", headers=auth_headers)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert all(i["id"] != inv["id"] for i in items), "pending 不应出现在 active 列表"

    # 列表 status_filter=pending_review 应包含
    r3 = await client.get(
        "/api/v1/invoices/?status_filter=pending_review", headers=auth_headers
    )
    items = r3.json()["items"]
    assert any(i["id"] == inv["id"] for i in items)

    # 清理
    inv_id = inv["id"]
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 2：去重（409）
# ===================================================================


@pytest.mark.asyncio
async def test_archive_dedup_returns_409(client, auth_headers, db_session, cleanup_invoices):
    code, number = "011002000111", "20000002"
    r1 = await _archive(client, auth_headers, code=code, number=number, file_hash=hashlib.sha256(b"d1").hexdigest())
    assert r1["status"] == 200

    # 第二次同 code+number → 409
    r2 = await _archive(client, auth_headers, code=code, number=number, file_hash=hashlib.sha256(b"d2").hexdigest())
    assert r2["status"] == 409, r2
    assert r2["body"]["code"] == "INVOICE_DUPLICATE"

    # 清理
    from app.models import Invoice
    await db_session.execute(
        delete(Invoice).where(
            Invoice.invoice_code == code,
            Invoice.invoice_number == number,
        )
    )
    await db_session.commit()


# ===================================================================
# 用例 3：详情
# ===================================================================


@pytest.mark.asyncio
async def test_get_invoice_detail(client, auth_headers, db_session, cleanup_invoices):
    r = await _archive(client, auth_headers, number="30000003", file_hash=hashlib.sha256(b"d3").hexdigest())
    inv_id = r["body"]["id"]

    r2 = await client.get(f"/api/v1/invoices/{inv_id}", headers=auth_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == inv_id
    assert body["file_url"] == "s3://invoices/test/sample.pdf"
    assert body["file_hash"]
    assert "updated_at" in body
    assert "user_id" in body

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 4：编辑字段
# ===================================================================


@pytest.mark.asyncio
async def test_update_invoice_fields(client, auth_headers, db_session, cleanup_invoices):
    r = await _archive(client, auth_headers, number="40000004", file_hash=hashlib.sha256(b"d4").hexdigest())
    inv_id = r["body"]["id"]

    r2 = await client.patch(
        f"/api/v1/invoices/{inv_id}",
        json={"remark": "测试备注", "amount_incl_tax": "1200.00"},
        headers=auth_headers,
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["remark"] == "测试备注"
    assert float(body["amount_incl_tax"]) == 1200.00

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 5：编辑触发去重校验
# ===================================================================


@pytest.mark.asyncio
async def test_update_changes_code_number_triggers_dedup(
    client, auth_headers, db_session, cleanup_invoices
):
    r1 = await _archive(client, auth_headers, number="50000005", file_hash=hashlib.sha256(b"d5a").hexdigest())
    r2 = await _archive(client, auth_headers, number="50000006", file_hash=hashlib.sha256(b"d5b").hexdigest())
    inv_id_1 = r1["body"]["id"]
    inv_id_2 = r2["body"]["id"]

    # 改 inv2 的 number 到 inv1 的 number → 409
    r3 = await client.patch(
        f"/api/v1/invoices/{inv_id_2}",
        json={"invoice_number": "50000005"},
        headers=auth_headers,
    )
    assert r3.status_code == 409
    assert r3.json()["code"] == "INVOICE_DUPLICATE"

    # 清理
    from app.models import Invoice
    await db_session.execute(
        delete(Invoice).where(Invoice.id.in_([UUID(inv_id_1), UUID(inv_id_2)]))
    )
    await db_session.commit()


# ===================================================================
# 用例 6：pending → active 确认
# ===================================================================


@pytest.mark.asyncio
async def test_confirm_invoice_pending_to_active(
    client, auth_headers, db_session, cleanup_invoices
):
    r = await _archive(client, auth_headers, number="60000006", file_hash=hashlib.sha256(b"d6").hexdigest())
    inv_id = r["body"]["id"]
    assert r["body"]["status"] == "pending_review"

    r2 = await client.post(
        f"/api/v1/invoices/{inv_id}/confirm",
        json={},
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"

    # 重复 confirm → 409
    r3 = await client.post(
        f"/api/v1/invoices/{inv_id}/confirm",
        json={},
        headers=auth_headers,
    )
    assert r3.status_code == 409
    assert r3.json()["code"] == "ALREADY_CONFIRMED"

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 7：软删
# ===================================================================


@pytest.mark.asyncio
async def test_soft_delete_invoice(client, auth_headers, db_session, cleanup_invoices):
    r = await _archive(client, auth_headers, number="70000007", file_hash=hashlib.sha256(b"d7").hexdigest())
    inv_id = r["body"]["id"]

    r2 = await client.delete(f"/api/v1/invoices/{inv_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["deleted"] is True

    # 列表应不显示
    r3 = await client.get("/api/v1/invoices/", headers=auth_headers)
    assert all(i["id"] != inv_id for i in r3.json()["items"])

    # 详情应 404
    r4 = await client.get(f"/api/v1/invoices/{inv_id}", headers=auth_headers)
    assert r4.status_code == 404

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 8：行级权限 - 员工看不到别人的
# ===================================================================


@pytest.mark.asyncio
async def test_employee_cannot_see_others_invoices(
    client, auth_headers, employee_headers, db_session, cleanup_invoices
):
    # admin 创建一条
    r = await _archive(client, auth_headers, number="80000008", file_hash=hashlib.sha256(b"d8").hexdigest())
    inv_id = r["body"]["id"]

    # employee 列表里不应看到
    r2 = await client.get("/api/v1/invoices/", headers=employee_headers)
    assert all(i["id"] != inv_id for i in r2.json()["items"])

    # employee 直接拿详情 → 404（行级隔离）
    r3 = await client.get(f"/api/v1/invoices/{inv_id}", headers=employee_headers)
    assert r3.status_code == 404

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 9：preview/by-hash
# ===================================================================


@pytest.mark.asyncio
async def test_preview_by_hash_processing_then_ready(
    client, auth_headers, db_session, cleanup_invoices
):
    target_hash = hashlib.sha256(b"unique-hash-9").hexdigest()

    # 第一次查：processing（不存在）
    r = await client.get(f"/api/v1/invoices/preview/by-hash/{target_hash}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "processing"

    # 创建一条该 hash
    r2 = await _archive(client, auth_headers, number="90000009", file_hash=target_hash)
    inv_id = r2["body"]["id"]

    # 再查：ready
    r3 = await client.get(f"/api/v1/invoices/preview/by-hash/{target_hash}", headers=auth_headers)
    assert r3.status_code == 200
    body = r3.json()
    assert body["status"] == "ready"
    assert body["invoice"]["id"] == inv_id

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()


# ===================================================================
# 用例 10：审计日志写入
# ===================================================================


@pytest.mark.asyncio
async def test_audit_log_written_on_confirm(
    client, auth_headers, db_session, cleanup_invoices
):
    from app.models import AuditLog, Invoice

    # 创建
    r = await _archive(client, auth_headers, number="10000010", file_hash=hashlib.sha256(b"d10").hexdigest())
    inv_id = r["body"]["id"]

    # confirm
    r2 = await client.post(
        f"/api/v1/invoices/{inv_id}/confirm",
        json={},
        headers=auth_headers,
    )
    assert r2.status_code == 200

    # 查 audit_logs
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.target_id == UUID(inv_id),
            AuditLog.operation_type == "confirm_invoice",
        )
    )
    logs = list(result.scalars().all())
    assert len(logs) == 1
    log = logs[0]
    assert log.operation_type == "confirm_invoice"
    assert log.before_value["status"] == "pending_review"
    assert log.after_value["status"] == "active"

    # 清理
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.execute(
        delete(AuditLog).where(AuditLog.target_id == UUID(inv_id))
    )
    await db_session.commit()


# ===================================================================
# 用例 11：file URL 端点
# ===================================================================


@pytest.mark.asyncio
async def test_get_invoice_file_url(client, auth_headers, db_session, cleanup_invoices):
    r = await _archive(client, auth_headers, number="11000011", file_hash=hashlib.sha256(b"d11").hexdigest())
    inv_id = r["body"]["id"]

    r2 = await client.get(
        f"/api/v1/invoices/{inv_id}/file?expires=600",
        headers=auth_headers,
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["expires_in"] == 600
    assert body["url"]

    # 清理
    from app.models import Invoice
    await db_session.execute(delete(Invoice).where(Invoice.id == UUID(inv_id)))
    await db_session.commit()
