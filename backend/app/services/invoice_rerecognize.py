"""人工触发：按原件重新识别发票字段并写回档案。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.services.audit_service import write_audit_log
from app.services.chat_file_service import chat_file_service
from app.services.invoice_service import invoice_service
from app.services.invoice_vision_service import invoice_vision_service
from app.services.ocr_service import InvoiceOCRResult
from app.services.storage_service import storage_service

if TYPE_CHECKING:
    from app.models import Invoice, User

logger = logging.getLogger(__name__)


def _snapshot(inv: "Invoice") -> dict:
    """审计用字段快照。"""
    return {
        "id": str(inv.id),
        "status": inv.status,
        "invoice_code": inv.invoice_code,
        "invoice_number": inv.invoice_number,
        "amount_incl_tax": float(inv.amount_incl_tax) if inv.amount_incl_tax is not None else None,
    }


async def rerecognize_invoice(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user: "User",
    invoice_id: UUID,
) -> "Invoice":
    """按原件重新抽取字段，覆盖当前档案；不改变归档状态。"""
    inv = await invoice_service.get(db, tenant_id, invoice_id, user=user)
    if await invoice_service.sidepanel_archive_status(db, inv) == "archived":
        raise BusinessError("该发票已归档，不再重新识别", code="INVOICE_ALREADY_ARCHIVED")
    if not inv.file_url:
        raise BusinessError("没有原件，无法重新识别", code="INVOICE_FILE_MISSING")

    chat_file = await chat_file_service.latest_for_invoice(db, inv.id)
    filename = (
        chat_file.original_filename
        if chat_file and chat_file.original_filename
        else inv.file_url.rsplit("/", 1)[-1]
    )
    content_type = chat_file.content_type if chat_file else None

    try:
        file_bytes = storage_service.download_bytes(inv.file_url)
    except Exception as exc:
        raise BusinessError(f"下载原件失败：{exc}", code="INVOICE_FILE_DOWNLOAD") from exc

    try:
        result, _source = await invoice_vision_service.recognize(
            file_bytes,
            content_type=content_type,
            filename=filename,
            db=db,
            tenant_id=str(tenant_id),
        )
    except Exception as exc:
        raise BusinessError(f"重新识别失败：{exc}", code="INVOICE_RECOGNIZE_FAILED") from exc

    if not isinstance(result, InvoiceOCRResult):
        raise BusinessError("识别结果无效", code="INVOICE_RECOGNIZE_FAILED")

    before = _snapshot(inv)
    inv.invoice_title = result.invoice_title
    inv.company = result.company
    inv.tax_id = result.tax_id
    inv.invoice_code = result.invoice_code
    inv.invoice_number = result.invoice_number
    inv.invoice_date = result.invoice_date
    inv.amount_excl_tax = result.amount_excl_tax
    inv.tax_amount = result.tax_amount
    inv.amount_incl_tax = result.amount_incl_tax
    inv.invoice_type = result.invoice_type
    inv.seller = result.seller
    inv.buyer = result.buyer
    inv.ocr_confidence = result.confidence
    await db.flush()
    await db.refresh(inv)

    await write_audit_log(
        db,
        tenant_id=tenant_id,
        user_id=user.id,
        operation_type="invoice.rerecognize",
        target_type="invoice",
        target_id=inv.id,
        before=before,
        after=_snapshot(inv),
    )
    await db.commit()

    if chat_file is not None:
        await chat_file_service.mark(
            db,
            chat_file.id,
            recognize_status="succeeded",
            recognize_error=None,
            extract_result={
                "invoice_code": inv.invoice_code,
                "invoice_number": inv.invoice_number,
            },
        )
    logger.info("invoice rerecognized id=%s number=%s", inv.id, inv.invoice_number)
    return inv
