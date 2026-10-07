"""合同归档服务：列表、详情、待归档、确认归档、软删。

与发票一致的两阶段：
- create_pending: 审查完成后写入待归档（status=pending_review），不去重
- confirm: 用户点击确认后才归档为 active；此时按 file_hash 查重
Agent / 审查链路不得直接写 active。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.entities import mark_contract_archived
from app.core.exceptions import BusinessError, ConflictError, ForbiddenError, NotFoundError
from app.services.audit_service import write_audit_log

if TYPE_CHECKING:
    from app.models import Contract, User

logger = logging.getLogger(__name__)


def _serialize_snapshot(row: "Contract") -> dict[str, Any]:
    """审计用合同字段快照。"""
    return {
        "contract_name": row.contract_name,
        "contract_no": row.contract_no,
        "party_a": row.party_a,
        "party_b": row.party_b,
        "amount": float(row.amount) if row.amount is not None else None,
        "risk_level": row.risk_level,
        "status": row.status,
        "file_hash": row.file_hash,
    }


def _parse_date(value: Any) -> date | None:
    """接受 YYYY-MM-DD / ISO 字符串 / date。"""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    # 2026/09/27 08:00 或 2026-09-27
    matched = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if matched:
        return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_amount(value: Any) -> Decimal | None:
    """金额转 Decimal。"""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").replace("¥", "").replace("￥", "").strip())
    except (InvalidOperation, ValueError):
        return None


def infer_risk_level(review_result: dict | None, explicit: str | None = None) -> str:
    """侧栏可能没带 risk_level，从审查摘要/违规项推断。"""
    if explicit in {"high", "medium", "low"}:
        return explicit
    result = review_result if isinstance(review_result, dict) else {}
    nested = result.get("risk_level")
    if nested in {"high", "medium", "low"}:
        return nested
    violations = result.get("violations") or []
    severities = {
        str(item.get("severity") or "").lower()
        for item in violations
        if isinstance(item, dict)
    }
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    summary = str(result.get("summary") or "")
    if "高风险" in summary or "极高风险" in summary:
        return "high"
    if "中风险" in summary:
        return "medium"
    return "low"


class ContractService:
    """合同档案 CRUD。"""

    async def list_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        user: "User",
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        risk_level: str | None = None,
        status_filter: str = "active",
    ) -> tuple[list["Contract"], int]:
        """当前租户合同列表（分页）；员工只看自己的。"""
        from app.models import Contract

        page = max(1, page)
        page_size = min(100, max(1, page_size))

        conditions = [Contract.tenant_id == tenant_id]
        if status_filter:
            conditions.append(Contract.status == status_filter)
        else:
            conditions.append(Contract.status != "deleted")
        if user.role == "employee":
            conditions.append(Contract.user_id == user.id)
        if risk_level:
            conditions.append(Contract.risk_level == risk_level)
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Contract.contract_name.ilike(like),
                    Contract.party_a.ilike(like),
                    Contract.party_b.ilike(like),
                    Contract.contract_no.ilike(like),
                )
            )

        where = and_(*conditions)
        total = (
            await db.execute(select(func.count()).select_from(Contract).where(where))
        ).scalar_one()
        offset = (page - 1) * page_size
        rows = (
            await db.execute(
                select(Contract)
                .where(where)
                .order_by(Contract.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def count_by_risk(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        user: "User",
        status_filter: str = "active",
    ) -> dict[str, int]:
        """按风险等级统计可见合同数（不受列表 search/risk 筛选影响）。"""
        from app.models import Contract

        conditions = [Contract.tenant_id == tenant_id]
        if status_filter:
            conditions.append(Contract.status == status_filter)
        else:
            conditions.append(Contract.status != "deleted")
        if user.role == "employee":
            conditions.append(Contract.user_id == user.id)

        rows = (
            await db.execute(
                select(Contract.risk_level, func.count())
                .where(*conditions)
                .group_by(Contract.risk_level)
            )
        ).all()

        counts = {"high": 0, "medium": 0, "low": 0}
        for level, n in rows:
            key = level or "low"
            if key in counts:
                counts[key] = int(n)
            else:
                # 未知等级并入 low，避免卡片总和不对
                counts["low"] += int(n)
        return counts

    async def list_for_export(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        user: "User",
        search: str | None = None,
        risk_level: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list["Contract"], int]:
        """导出用分页列表：排除 deleted；员工仅本人；无 200 条硬上限。"""
        from app.models import Contract

        page = max(1, page)
        page_size = min(100, max(1, page_size))

        conditions = [
            Contract.tenant_id == tenant_id,
            Contract.status != "deleted",
        ]
        if user.role == "employee":
            conditions.append(Contract.user_id == user.id)
        if risk_level:
            conditions.append(Contract.risk_level == risk_level)
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Contract.contract_name.ilike(like),
                    Contract.party_a.ilike(like),
                    Contract.party_b.ilike(like),
                    Contract.contract_no.ilike(like),
                )
            )

        where = and_(*conditions)
        total = (
            await db.execute(select(func.count()).select_from(Contract).where(where))
        ).scalar_one()
        offset = (page - 1) * page_size
        rows = (
            await db.execute(
                select(Contract)
                .where(where)
                .order_by(Contract.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def get(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        contract_id: UUID,
        *,
        user: "User",
        include_deleted: bool = False,
    ) -> "Contract":
        """合同详情；校验租户与可见性。"""
        from app.models import Contract

        row = await db.get(Contract, contract_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError("合同不存在", code="CONTRACT_NOT_FOUND")
        if not include_deleted and row.status == "deleted":
            raise NotFoundError("合同不存在", code="CONTRACT_NOT_FOUND")
        if user.role == "employee" and row.user_id != user.id:
            raise ForbiddenError("无权查看该合同", code="CONTRACT_FORBIDDEN")
        return row

    async def _find_pending_by_hash(
        self, db: AsyncSession, tenant_id: UUID, file_hash: str
    ) -> "Contract | None":
        """找同一文件、尚未人工确认的合同。"""
        from app.models import Contract

        return (
            await db.execute(
                select(Contract).where(
                    Contract.tenant_id == tenant_id,
                    Contract.file_hash == file_hash,
                    Contract.status == "pending_review",
                )
            )
        ).scalars().first()

    async def _find_archived_by_hash(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        file_hash: str,
        *,
        exclude_id: UUID | None = None,
    ) -> "Contract | None":
        """只在已归档（active）记录里按 file_hash 查重。"""
        from app.models import Contract

        stmt = select(Contract).where(
            Contract.tenant_id == tenant_id,
            Contract.file_hash == file_hash,
            Contract.status == "active",
        )
        if exclude_id is not None:
            stmt = stmt.where(Contract.id != exclude_id)
        return (await db.execute(stmt)).scalars().first()

    async def get_archived_by_hash(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        file_hash: str,
        *,
        user: "User | None" = None,
    ) -> "Contract | None":
        """同一原件已归档则返回该合同，供跳过重复审查。"""
        from app.models import Contract

        if not file_hash:
            return None
        conditions = [
            Contract.tenant_id == tenant_id,
            Contract.file_hash == file_hash,
            Contract.status == "active",
        ]
        if user is not None and user.role == "employee":
            conditions.append(Contract.user_id == user.id)
        return (
            await db.execute(
                select(Contract)
                .where(*conditions)
                .order_by(Contract.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

    async def sidepanel_archive_status(self, db: AsyncSession, row: "Contract") -> str:
        """侧栏归档态：本合同已归档，或档案里已有相同文件。"""
        if row.status == "active":
            return "archived"
        if row.file_hash:
            dup = await self._find_archived_by_hash(
                db,
                row.tenant_id,
                row.file_hash,
                exclude_id=row.id,
            )
            if dup is not None:
                return "archived"
        return "pending"

    def _build_pending_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """从审查/侧栏数据组装待归档字段（不含 tenant/user）。"""
        file_url = (data.get("file_url") or "").strip()
        file_hash = (data.get("file_hash") or "").strip()
        if not file_url or not file_hash:
            raise BusinessError("缺少文件地址，无法保存识别结果", code="CONTRACT_FILE_REQUIRED")

        review_result = data.get("review_result")
        if review_result is not None and not isinstance(review_result, dict):
            review_result = {"summary": str(review_result), "violations": []}

        risk_level = infer_risk_level(review_result, data.get("risk_level"))
        return {
            "contract_name": data.get("contract_name") or None,
            "contract_no": data.get("contract_no") or None,
            "party_a": data.get("party_a") or None,
            "party_b": data.get("party_b") or None,
            "sign_date": _parse_date(data.get("sign_date")),
            "amount": _parse_amount(data.get("amount")),
            "key_clauses": data.get("key_clauses") or None,
            "review_result": review_result,
            "risk_level": risk_level,
            "file_url": file_url,
            "file_hash": file_hash,
            "parse_status": "done",
            "status": "pending_review",
        }

    async def _link_chat_file(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        chat_file_id: UUID | None,
        contract_id: UUID,
    ) -> None:
        """回写聊天附件，重开会话可还原侧栏。"""
        from app.models import ChatFile

        if chat_file_id is None:
            return
        chat_file = await db.get(ChatFile, chat_file_id)
        if (
            chat_file is not None
            and chat_file.tenant_id == tenant_id
            and chat_file.user_id == user_id
        ):
            chat_file.contract_id = contract_id

    async def create_pending(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        data: dict[str, Any],
        chat_file_id: UUID | None = None,
    ) -> "Contract":
        """审查完成后写入待归档。不在这里做归档去重，也不把 status 擅自改成 active。

        若附件已关联合同（含已归档），刷新识别字段与审查摘要，保留原 status。
        """
        from app.models import ChatFile, Contract

        fields = self._build_pending_fields(data)
        file_hash = fields["file_hash"]

        existing: Contract | None = None
        # 优先更新本附件已关联的合同，避免摘要写到另一条 pending、侧栏仍读旧档案
        if chat_file_id is not None:
            chat_file = await db.get(ChatFile, chat_file_id)
            if (
                chat_file is not None
                and chat_file.tenant_id == tenant_id
                and chat_file.user_id == user_id
                and chat_file.contract_id is not None
            ):
                linked = await db.get(Contract, chat_file.contract_id)
                if (
                    linked is not None
                    and linked.tenant_id == tenant_id
                    and linked.status != "deleted"
                ):
                    existing = linked

        if existing is None:
            existing = await self._find_pending_by_hash(db, tenant_id, file_hash)

        if existing:
            keep_status = existing.status
            for key, value in fields.items():
                if key == "status":
                    continue
                setattr(existing, key, value)
            # 仅未归档的保持/回到 pending_review；已归档只刷新识别内容
            if keep_status != "active":
                existing.status = "pending_review"
            row = existing
            await db.flush()
            await db.refresh(row)
            logger.info(
                "contract recognition refreshed: id=%s hash=%s status=%s",
                row.id,
                file_hash[:12],
                row.status,
            )
        else:
            row = Contract(tenant_id=tenant_id, user_id=user_id, **fields)
            db.add(row)
            await db.flush()
            await db.refresh(row)
            await write_audit_log(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                operation_type="contract.create_pending",
                target_type="contract",
                target_id=row.id,
                after=_serialize_snapshot(row),
            )
            logger.info(
                "contract created pending: id=%s hash=%s risk=%s",
                row.id,
                file_hash[:12],
                row.risk_level,
            )

        await self._link_chat_file(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            chat_file_id=chat_file_id,
            contract_id=row.id,
        )
        return row

    async def archive(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        data: dict[str, Any],
        chat_file_id: UUID | None = None,
    ) -> "Contract":
        """兼容旧 /contracts/archive：仅写入 pending_review，不代替用户确认。"""
        return await self.create_pending(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            data=data,
            chat_file_id=chat_file_id,
        )

    async def confirm(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        contract_id: UUID,
        fields: dict[str, Any] | None = None,
    ) -> "Contract":
        """用户确认：pending_review → active；此时按 file_hash 查重。"""
        row = await self.get(db, tenant_id, contract_id, user=user)
        if row.status == "active":
            raise ConflictError("合同已归档，无需重复确认", code="ALREADY_CONFIRMED")
        if row.status == "deleted":
            raise NotFoundError("合同不存在", code="CONTRACT_NOT_FOUND")
        if row.status != "pending_review":
            raise BusinessError(
                f"合同状态不可确认归档：{row.status}",
                code="CONTRACT_CONFIRM_INVALID_STATUS",
            )

        before = _serialize_snapshot(row)

        # 最后一次字段更新（审查摘要由识别写入，确认时不允许前端覆盖）
        if fields:
            editable = {
                "contract_name",
                "contract_no",
                "party_a",
                "party_b",
                "sign_date",
                "amount",
                "key_clauses",
                "risk_level",
            }
            for key, value in fields.items():
                if key not in editable:
                    continue
                if key == "sign_date":
                    setattr(row, key, _parse_date(value))
                elif key == "amount":
                    setattr(row, key, _parse_amount(value))
                elif key == "risk_level":
                    setattr(row, key, infer_risk_level(row.review_result, value))
                elif isinstance(value, str):
                    setattr(row, key, value or None)
                else:
                    setattr(row, key, value)

        if row.file_hash:
            dup = await self._find_archived_by_hash(
                db, tenant_id, row.file_hash, exclude_id=row.id
            )
            if dup is not None:
                raise ConflictError(
                    "归档失败：相同文件的合同已在档案中",
                    code="CONTRACT_DUPLICATE",
                )

        row.status = "active"
        await db.flush()
        await db.refresh(row)

        await write_audit_log(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            operation_type="contract.confirm",
            target_type="contract",
            target_id=row.id,
            before=before,
            after=_serialize_snapshot(row),
        )
        await db.commit()
        logger.info("contract confirmed id=%s hash=%s", row.id, (row.file_hash or "")[:12])
        await mark_contract_archived(db, row.id)
        return row

    async def refresh_review(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        contract_id: UUID,
        data: dict[str, Any],
        chat_file_id: UUID | None = None,
    ) -> "Contract":
        """用新审查结果覆盖指定合同；已归档只刷新内容，不改 status。"""
        row = await self.get(db, tenant_id, contract_id, user=user)
        before = _serialize_snapshot(row)
        fields = self._build_pending_fields(data)
        keep_status = row.status
        for key, value in fields.items():
            if key in {"status", "file_url", "file_hash"}:
                continue
            setattr(row, key, value)
        if keep_status != "active":
            row.status = "pending_review"
        await db.flush()
        await db.refresh(row)
        await self._link_chat_file(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            chat_file_id=chat_file_id,
            contract_id=row.id,
        )
        await write_audit_log(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            operation_type="contract.rereview",
            target_type="contract",
            target_id=row.id,
            before=before,
            after=_serialize_snapshot(row),
        )
        await db.commit()
        logger.info(
            "contract review refreshed: id=%s hash=%s status=%s",
            row.id,
            (row.file_hash or "")[:12],
            row.status,
        )
        return row

    async def soft_delete(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        contract_id: UUID,
    ) -> None:
        """软删合同档案。"""
        row = await self.get(db, tenant_id, contract_id, user=user)
        if user.role == "employee" and row.user_id != user.id:
            raise ForbiddenError("无权删除该合同", code="CONTRACT_FORBIDDEN")
        row.status = "deleted"
        await write_audit_log(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            operation_type="contract.delete",
            target_type="contract",
            target_id=row.id,
            before={"status": "active"},
            after={"status": "deleted"},
        )
        await db.commit()


contract_service = ContractService()


# ================ 敏感字段脱敏（审查链路仍可用） ================

def mask_sensitive(text: str) -> str:
    """脱敏处理：税号、银行账号、手机号、身份证。"""
    text = re.sub(r"\d{15,20}", "[TAX_ID]", text)
    text = re.sub(r"\d{16,19}", "[BANK_ACCOUNT]", text)
    text = re.sub(r"1[3-9]\d{9}", "[PHONE]", text)
    text = re.sub(r"\d{17}[\dXx]", "[ID_CARD]", text)
    return text


async def review_contract(text_content: str, tenant_id: str, db) -> dict:
    """审查合同合规性（旧入口保留，聊天流已走 llm_service.stream）。"""
    import json

    from app.services.llm_service import llm_service
    from app.services.rag_service import rag_service

    masked = mask_sensitive(text_content)
    rules = await rag_service.retrieve_rules(db, tenant_id)
    rules_text = "\n".join(f"- {r}" for r in rules)
    prompt = f"""你是合同合规审查专家。请根据以下规则审查合同。

[规则]
{rules_text}

[合同内容]
{masked}

返回 JSON：
{{
  "violations": [{{"clause": "...", "issue": "...", "severity": "high/medium/low"}}],
  "risk_level": "high/medium/low",
  "summary": "..."
}}
"""
    result = await llm_service.invoke(
        messages=[{"role": "user", "content": prompt}],
        scene="contract_review",
        response_format={"type": "json_object"},
    )
    return json.loads(result)
