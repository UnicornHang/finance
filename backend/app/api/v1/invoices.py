"""发票归档 API。

实现端点：
- GET    /invoices/                           列表（分页+筛选）
- POST   /invoices/archive                    兼容老 API：直接 JSON 入库
- GET    /invoices/preview/by-hash/{hash}    前端轮询查 OCR 结果
- GET    /invoices/{invoice_id}               详情
- PATCH  /invoices/{invoice_id}               编辑字段
- POST   /invoices/{invoice_id}/confirm       pending_review → active
- DELETE /invoices/{invoice_id}               软删
- GET    /invoices/{invoice_id}/file          预签名下载 URL

通用文件上传走 `POST /api/v1/files/upload`（只存 MinIO，不触发 OCR/审查）；
OCR 任务由 chat_service 在用户发送消息后根据 LLM 语义判断派发。
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services.invoice_service import invoice_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ================ Schemas ================

class InvoiceUpdate(BaseModel):
    invoice_title: str | None = None
    company: str | None = None
    tax_id: str | None = None
    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount_excl_tax: Decimal | None = None
    tax_amount: Decimal | None = None
    amount_incl_tax: Decimal | None = None
    invoice_type: str | None = None
    seller: str | None = None
    buyer: str | None = None
    remark: str | None = None


class InvoiceArchiveRequest(BaseModel):
    """兼容老 API 的发票归档请求体（直接 JSON 入库）。"""
    invoice_title: str | None = None
    company: str | None = None
    tax_id: str | None = None
    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount_excl_tax: Decimal | None = None
    tax_amount: Decimal | None = None
    amount_incl_tax: Decimal | None = None
    invoice_type: str | None = None
    seller: str | None = None
    buyer: str | None = None
    remark: str | None = None
    file_url: str = ""
    file_hash: str = ""


# ================ Helpers ================

def _serialize(inv) -> dict[str, Any]:
    """Invoice → 响应字典。"""
    return {
        "id": str(inv.id),
        "invoice_title": inv.invoice_title,
        "company": inv.company,
        "tax_id": inv.tax_id,
        "invoice_code": inv.invoice_code,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "amount_excl_tax": float(inv.amount_excl_tax) if inv.amount_excl_tax is not None else None,
        "tax_amount": float(inv.tax_amount) if inv.tax_amount is not None else None,
        "amount_incl_tax": float(inv.amount_incl_tax) if inv.amount_incl_tax is not None else None,
        "invoice_type": inv.invoice_type,
        "seller": inv.seller,
        "buyer": inv.buyer,
        "remark": inv.remark,
        "file_url": inv.file_url,
        "file_hash": inv.file_hash,
        "ocr_confidence": inv.ocr_confidence,
        "status": inv.status,
        "user_id": str(inv.user_id),
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
    }


# ================ Endpoints ================

@router.get("/")
async def list_invoices(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    invoice_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status_filter: str | None = Query(default="active"),
):
    """当前租户发票列表（员工仅看自己）。"""
    rows, total = await invoice_service.list_by_tenant(
        db,
        user.tenant_id,
        user=user,
        page=page,
        page_size=page_size,
        invoice_type=invoice_type,
        search=search,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
    )
    return {
        "items": [_serialize(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/archive")
async def archive_invoice(
    body: InvoiceArchiveRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """手动归档入口（兼容旧 API）。

    主路径走 POST /chat/stream + POST /invoices/{id}/confirm，
    此端点仅供直接 JSON 入库场景（无 OCR）。
    """
    inv = await invoice_service.archive(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        invoice_data=body.model_dump(),
    )
    await db.commit()
    return _serialize(inv)


@router.get("/preview/by-hash/{file_hash}")
async def preview_invoice_by_hash(
    file_hash: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """前端轮询：按 file_hash 查最近一张发票。

    返回：
    - {status: "processing"}：未找到（OCR 还在跑或失败）
    - {status: "ready", invoice: {...}}：OCR 完成且可编辑
    - {status: "not_found"}：确实不存在
    """
    inv = await invoice_service.get_by_hash(db, user.tenant_id, file_hash)
    if not inv:
        # 区分 OCR 还在跑 vs 真的失败/不存在
        # 简化策略：5 秒内的请求视为 processing，超过返回 not_found
        # 这里先返回 processing，让前端继续轮询（最多 30 次）
        return {"status": "processing"}
    return {"status": "ready", "invoice": _serialize(inv)}


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """发票详情。"""
    inv = await invoice_service.get(db, user.tenant_id, invoice_id, user=user)
    return _serialize(inv)


@router.patch("/{invoice_id}")
async def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """编辑发票字段（不改状态）。"""
    fields = body.model_dump(exclude_none=True)
    inv = await invoice_service.update_fields(
        db,
        tenant_id=user.tenant_id,
        user=user,
        invoice_id=invoice_id,
        fields=fields,
    )
    return _serialize(inv)


@router.post("/{invoice_id}/confirm")
async def confirm_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """用户最后确认：pending_review → active。

    Body 可携带最后一次编辑字段。
    """
    fields = body.model_dump(exclude_none=True)
    inv = await invoice_service.confirm(
        db,
        tenant_id=user.tenant_id,
        user=user,
        invoice_id=invoice_id,
        fields=fields or None,
    )
    return _serialize(inv)


@router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """软删：status='deleted'，保留审计。"""
    await invoice_service.soft_delete(
        db,
        tenant_id=user.tenant_id,
        user=user,
        invoice_id=invoice_id,
    )
    return {"deleted": True, "invoice_id": str(invoice_id)}


@router.get("/{invoice_id}/file")
async def get_invoice_file(
    invoice_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    expires: int = Query(default=3600, ge=60, le=86400),
):
    """返回 MinIO 预签名下载 URL。"""
    url = await invoice_service.get_presigned_download_url(
        db,
        tenant_id=user.tenant_id,
        user=user,
        invoice_id=invoice_id,
        expires_seconds=expires,
    )
    return {"url": url, "expires_in": expires}