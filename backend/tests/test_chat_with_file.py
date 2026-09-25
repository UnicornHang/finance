"""Chat 文件上传 + OCR 任务集成测试（Phase A）。

覆盖：
- POST /chat/stream multipart 上传 → SSE 含 sidepanel{status:processing}
- OCR pipeline 直接调用：下载 → OCR → 写 Invoice (pending_review)
- OCR pipeline 二次相同 file → ConflictError，不重复写库
"""

from __future__ import annotations

import asyncio
import hashlib
import io
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.exceptions import ConflictError
from app.services.ocr_service import InvoiceOCRResult


# ===================================================================
# 辅助：构造一个最小有效 PDF（仅用于 multipart 上传，OCR 阶段用 mock 替代）
# ===================================================================


def _make_pdf_bytes() -> bytes:
    """构造一个 8-byte 的占位 PDF（OCR 不解析，测试只走 pipeline）。"""
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n%%EOF"


# ===================================================================
# 用例 1：SSE 流收到 sidepanel{processing}
# ===================================================================


@pytest.mark.asyncio
async def test_stream_with_file_yields_processing_sidepanel(client, auth_headers):
    """上传文件 → SSE 立即推 sidepanel{processing} + text + done。

    不验证 OCR 真正完成（那需要 Celery worker + MinIO + 真 OCR Provider）。
    """
    payload = _make_pdf_bytes()
    files = {"file": ("test.pdf", io.BytesIO(payload), "application/pdf")}
    data = {"message": "请帮我识别这张发票"}

    collected = []
    async with client.stream(
        "POST",
        "/api/v1/chat/stream",
        headers=auth_headers,
        files=files,
        data=data,
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                import json
                try:
                    collected.append(json.loads(line[6:]))
                except Exception:
                    pass
            if len(collected) >= 5:
                break

    # 应包含 sidepanel{processing} 和 done
    types = [e.get("type") for e in collected]
    assert "done" in types
    sp_events = [e for e in collected if e.get("type") == "sidepanel"]
    assert len(sp_events) >= 1
    sp = sp_events[0]
    assert sp["payload"]["type"] == "invoice"
    assert sp["payload"]["data"]["status"] == "processing"
    assert "file_hash" in sp["payload"]["data"]
    assert "file_url" in sp["payload"]["data"]


@pytest.mark.asyncio
async def test_stream_empty_message_and_no_file_returns_400(client, auth_headers):
    """既无 message 也无 file → 400 EMPTY_INPUT。"""
    r = await client.post("/api/v1/chat/stream", headers=auth_headers, data={})
    assert r.status_code == 400
    assert r.json()["code"] == "EMPTY_INPUT"


@pytest.mark.asyncio
async def test_stream_text_only_no_sidepanel(client, auth_headers):
    """纯文本对话（无文件）→ 不应触发 sidepanel processing。

    注：实际流式响应依赖 LLM 调用，可能直接 done 或 text + done。
    """
    data = {"message": "你好"}
    collected = []
    async with client.stream(
        "POST", "/api/v1/chat/stream", headers=auth_headers, data=data
    ) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                import json
                try:
                    collected.append(json.loads(line[6:]))
                except Exception:
                    pass
            if len(collected) >= 10:
                break

    # 不应有 sidepanel
    sp_events = [e for e in collected if e.get("type") == "sidepanel"]
    assert len(sp_events) == 0


# ===================================================================
# 用例 4：OCR pipeline 直接调用（mock OCR provider + MinIO）
# ===================================================================


@pytest.mark.asyncio
async def test_ocr_pipeline_writes_pending_invoice(db_session):
    """直接调 _run_ocr_pipeline，验证入库 status=pending_review。"""
    from app.models import Invoice
    from app.tasks.ocr_task import _run_ocr_pipeline

    # 准备：先上一个真实文件到 MinIO（或 mock download）
    fake_bytes = _make_pdf_bytes()
    file_hash = hashlib.sha256(fake_bytes).hexdigest()

    tenant_id = uuid4()
    user_id = uuid4()

    # mock 三个外部依赖：MinIO download、OCR provider
    mock_result = InvoiceOCRResult(
        invoice_title="Mock 发票",
        company="Mock 公司",
        tax_id="91110000MOCK",
        invoice_code="MOCK0001",
        invoice_number="MOCK00000001",
        invoice_date=date.today(),
        amount_excl_tax=Decimal("100.00"),
        tax_amount=Decimal("13.00"),
        amount_incl_tax=Decimal("113.00"),
        invoice_type="electronic",
        seller="Mock 销售方",
        buyer="Mock 购买方",
        confidence={"invoice_number": 0.99, "amount": 0.99},
    )

    async def fake_recognize(_bytes, **_kwargs):
        return mock_result, "llm"

    with patch("app.tasks.ocr_task._download_from_minio", return_value=fake_bytes), \
         patch("app.tasks.ocr_task.invoice_vision_service.recognize", fake_recognize):
        # file_url 必须能被 _parse_s3_url 解析
        file_url = "s3://invoices/test/mock.pdf"
        await _run_ocr_pipeline(
            tenant_id=tenant_id,
            user_id=user_id,
            file_url=file_url,
            file_hash=file_hash,
            user_message=None,
        )

    # 验证
    result = await db_session.execute(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.file_hash == file_hash,
        )
    )
    inv = result.scalars().first()
    assert inv is not None
    assert inv.status == "pending_review"
    assert inv.invoice_number == "MOCK00000001"
    assert float(inv.amount_incl_tax) == 113.00

    # 清理
    await db_session.execute(delete(Invoice).where(Invoice.tenant_id == tenant_id))
    await db_session.commit()


# ===================================================================
# 用例 5：OCR pipeline 重复 → ConflictError，不写第二条
# ===================================================================


@pytest.mark.asyncio
async def test_ocr_pipeline_dedup_blocks_duplicate(db_session):
    """第二次相同 (code+number) 触发 ConflictError。"""
    from app.models import Invoice
    from app.tasks.ocr_task import _run_ocr_pipeline

    fake_bytes = _make_pdf_bytes()
    file_hash_1 = hashlib.sha256(b"first").hexdigest()
    file_hash_2 = hashlib.sha256(b"second").hexdigest()
    tenant_id = uuid4()
    user_id = uuid4()

    same_code = "DEDUP0001"
    same_number = "DEDUP00000001"

    mock_result = InvoiceOCRResult(
        invoice_title="重复测试",
        company="重复公司",
        tax_id="91110000DUP",
        invoice_code=same_code,
        invoice_number=same_number,
        invoice_date=date.today(),
        amount_excl_tax=Decimal("100.00"),
        tax_amount=Decimal("13.00"),
        amount_incl_tax=Decimal("113.00"),
        invoice_type="electronic",
        seller="销售",
        buyer="购买",
        confidence={},
    )

    async def fake_recognize(_bytes, **_kwargs):
        return mock_result, "llm"

    with patch("app.tasks.ocr_task._download_from_minio", return_value=fake_bytes), \
         patch("app.tasks.ocr_task.invoice_vision_service.recognize", fake_recognize):
        file_url = "s3://invoices/test/dedup.pdf"

        # 第一次：成功
        await _run_ocr_pipeline(
            tenant_id=tenant_id,
            user_id=user_id,
            file_url=file_url,
            file_hash=file_hash_1,
            user_message=None,
        )

        # 第二次：ConflictError
        with pytest.raises(ConflictError) as exc_info:
            await _run_ocr_pipeline(
                tenant_id=tenant_id,
                user_id=user_id,
                file_url=file_url,
                file_hash=file_hash_2,
                user_message=None,
            )
        assert exc_info.value.code == "INVOICE_DUPLICATE"

    # 验证只有一条
    result = await db_session.execute(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.invoice_code == same_code,
            Invoice.invoice_number == same_number,
        )
    )
    rows = list(result.scalars().all())
    assert len(rows) == 1

    # 清理
    await db_session.execute(delete(Invoice).where(Invoice.tenant_id == tenant_id))
    await db_session.commit()
