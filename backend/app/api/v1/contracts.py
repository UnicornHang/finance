"""合同归档 API。

与发票一致：
- 审查完成后写入 pending_review（Agent 不代替用户确认）
- 用户在右侧栏点「确定归档」→ POST /{id}/confirm → active
列表供管理后台「合同归档」使用。
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessError
from app.deps import get_current_user
from app.models import User
from app.services.contract_service import contract_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ContractArchiveRequest(BaseModel):
    """兼容旧入口：仅写入 pending_review，不直接 active。"""

    contract_name: str | None = None
    contract_no: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    sign_date: str | date | None = None
    amount: float | Decimal | None = None
    risk_level: str | None = None
    review_result: dict[str, Any] | None = None
    key_clauses: str | None = None
    file_url: str = Field(..., min_length=1)
    file_hash: str = Field(..., min_length=1)
    chat_file_id: UUID | None = None


class ContractConfirmRequest(BaseModel):
    """确认归档时可携带最后一次编辑字段（不含审查摘要，摘要以识别结果为准）。"""

    contract_name: str | None = None
    contract_no: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    sign_date: str | date | None = None
    amount: float | Decimal | None = None
    risk_level: str | None = None
    key_clauses: str | None = None


def _serialize(row) -> dict[str, Any]:
    """Contract → 前端 Contract 类型。"""
    return {
        "id": str(row.id),
        "contract_name": row.contract_name,
        "contract_no": row.contract_no,
        "party_a": row.party_a,
        "party_b": row.party_b,
        "sign_date": row.sign_date.isoformat() if row.sign_date else None,
        "effective_start": row.effective_start.isoformat() if row.effective_start else None,
        "effective_end": row.effective_end.isoformat() if row.effective_end else None,
        "amount": float(row.amount) if row.amount is not None else None,
        "key_clauses": row.key_clauses,
        "review_result": row.review_result,
        "risk_level": row.risk_level,
        "status": row.status,
        "file_url": row.file_url,
        "file_hash": row.file_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/")
async def list_contracts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
):
    """合同列表（管理后台）。"""
    rows = await contract_service.list_by_tenant(
        db,
        user.tenant_id,
        user=user,
        search=search,
        risk_level=risk_level,
    )
    return [_serialize(row) for row in rows]


@router.post("/archive")
async def archive_contract(
    body: ContractArchiveRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """兼容旧入口：仅写入 pending_review。主路径走审查流 + confirm。"""
    row = await contract_service.create_pending(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        data=body.model_dump(),
        chat_file_id=body.chat_file_id,
    )
    await db.commit()
    return _serialize(row)


@router.get("/{contract_id}")
async def get_contract(
    contract_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """合同详情 + 审查报告。"""
    row = await contract_service.get(db, user.tenant_id, contract_id, user=user)
    return _serialize(row)


@router.post("/{contract_id}/confirm")
async def confirm_contract(
    contract_id: UUID,
    body: ContractConfirmRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """用户确认：pending_review → active。Body 可带最后一次编辑。"""
    fields = body.model_dump(exclude_none=True)
    row = await contract_service.confirm(
        db,
        tenant_id=user.tenant_id,
        user=user,
        contract_id=contract_id,
        fields=fields or None,
    )
    return _serialize(row)


@router.post("/{contract_id}/review")
async def re_review_contract(contract_id: UUID):
    """重新审查合同（人工触发）。完整流水线后续迭代。"""
    raise BusinessError("重新审查尚未开放，请重新上传合同", code="CONTRACT_REVIEW_TODO")


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除合同（软删）。"""
    await contract_service.soft_delete(
        db,
        tenant_id=user.tenant_id,
        user=user,
        contract_id=contract_id,
    )
    return {"ok": True}
