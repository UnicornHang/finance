"""会话结构化记忆：规则写入，不每轮跑抽取 LLM。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatFile, SessionMemory

logger = logging.getLogger(__name__)

LAST_INTENT = "last_intent"
PENDING_TASK = "pending_task"
UPLOADED_INVOICES = "uploaded_invoices"
UPLOADED_CONTRACTS = "uploaded_contracts"
QUERIED_POLICIES = "queried_policies"


async def upsert_entity(
    db: AsyncSession, session_id: UUID, entity_type: str, entity_value: dict[str, Any]
) -> None:
    """按 session + type 覆盖写入 JSON 实体。"""
    stmt = select(SessionMemory).where(
        SessionMemory.session_id == session_id,
        SessionMemory.entity_type == entity_type,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        db.add(
            SessionMemory(
                session_id=session_id,
                entity_type=entity_type,
                entity_value=entity_value,
            )
        )
    else:
        row.entity_value = entity_value
    await db.commit()


async def _append_id(
    db: AsyncSession, session_id: UUID, entity_type: str, item_id: str
) -> None:
    """在 ids 列表末尾追加，去重。"""
    stmt = select(SessionMemory).where(
        SessionMemory.session_id == session_id,
        SessionMemory.entity_type == entity_type,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    ids: list[str] = []
    if row and isinstance(row.entity_value, dict):
        raw = row.entity_value.get("ids") or []
        if isinstance(raw, list):
            ids = [str(x) for x in raw]
    if item_id not in ids:
        ids.append(item_id)
    await upsert_entity(db, session_id, entity_type, {"ids": ids[-50:]})


async def set_last_intent(db: AsyncSession, session_id: UUID, intent: str) -> None:
    """记录本轮最终采用的意图，供下一轮追问继承。"""
    try:
        await upsert_entity(db, session_id, LAST_INTENT, {"value": intent})
    except Exception:
        logger.exception("set_last_intent failed session=%s", session_id)


async def remember_invoice_pending(
    db: AsyncSession, session_id: UUID, invoice_id: UUID
) -> None:
    """发票进入待归档。"""
    try:
        iid = str(invoice_id)
        await _append_id(db, session_id, UPLOADED_INVOICES, iid)
        await upsert_entity(
            db, session_id, PENDING_TASK, {"kind": "invoice_pending", "id": iid}
        )
    except Exception:
        logger.exception("remember_invoice_pending failed")


async def remember_contract_pending(
    db: AsyncSession, session_id: UUID, contract_id: UUID
) -> None:
    """合同进入待归档。"""
    try:
        cid = str(contract_id)
        await _append_id(db, session_id, UPLOADED_CONTRACTS, cid)
        await upsert_entity(
            db, session_id, PENDING_TASK, {"kind": "contract_pending", "id": cid}
        )
    except Exception:
        logger.exception("remember_contract_pending failed")


async def remember_policy_title(
    db: AsyncSession, session_id: UUID, title: str
) -> None:
    """记下本轮用到的制度标题。"""
    title = (title or "").strip()
    if not title:
        return
    try:
        stmt = select(SessionMemory).where(
            SessionMemory.session_id == session_id,
            SessionMemory.entity_type == QUERIED_POLICIES,
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        titles: list[str] = []
        if row and isinstance(row.entity_value, dict):
            raw = row.entity_value.get("titles") or []
            if isinstance(raw, list):
                titles = [str(x) for x in raw]
        if title not in titles:
            titles.append(title)
        await upsert_entity(
            db, session_id, QUERIED_POLICIES, {"titles": titles[-20:]}
        )
    except Exception:
        logger.exception("remember_policy_title failed")


async def _clear_pending_if_match(
    db: AsyncSession, session_id: UUID, kind: str, item_id: str
) -> None:
    """pending 指向该单据时清掉待办。"""
    stmt = select(SessionMemory).where(
        SessionMemory.session_id == session_id,
        SessionMemory.entity_type == PENDING_TASK,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row or not isinstance(row.entity_value, dict):
        return
    if row.entity_value.get("kind") == kind and str(row.entity_value.get("id")) == item_id:
        await upsert_entity(db, session_id, PENDING_TASK, {"kind": "none"})


async def mark_invoice_archived(db: AsyncSession, invoice_id: UUID) -> None:
    """确认归档后按 chat_files 找到会话并清除 pending。"""
    try:
        stmt = select(ChatFile.session_id).where(ChatFile.invoice_id == invoice_id)
        session_ids = [r[0] for r in (await db.execute(stmt)).all() if r[0]]
        iid = str(invoice_id)
        for sid in session_ids:
            await _clear_pending_if_match(db, sid, "invoice_pending", iid)
    except Exception:
        logger.exception("mark_invoice_archived failed invoice=%s", invoice_id)


async def mark_contract_archived(db: AsyncSession, contract_id: UUID) -> None:
    """确认归档后清除合同 pending。"""
    try:
        stmt = select(ChatFile.session_id).where(ChatFile.contract_id == contract_id)
        session_ids = [r[0] for r in (await db.execute(stmt)).all() if r[0]]
        cid = str(contract_id)
        for sid in session_ids:
            await _clear_pending_if_match(db, sid, "contract_pending", cid)
    except Exception:
        logger.exception("mark_contract_archived failed contract=%s", contract_id)
