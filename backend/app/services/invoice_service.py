"""发票归档服务 - CRUD + 去重 + 审计日志。

Phase A 范围：
- list_by_tenant: 列表（按角色过滤 + 分页 + 筛选）
- get: 详情
- get_by_hash: 前端轮询用
- create_pending: 识别完成后写入待归档（status=pending_review），不去重
- confirm: 用户确认后才归档；此时若档案已有相同代码+号码则失败
- update_fields: 编辑字段（不改 status），写审计
- soft_delete: 软删 + 审计
- get_presigned_download_url: 预签名下载 URL
"""

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.services.audit_service import write_audit_log
from app.services.storage_service import storage_service

if TYPE_CHECKING:
    from app.models import Invoice, User

logger = logging.getLogger(__name__)


class InvoiceService:
    """发票业务编排：CRUD + 业务规则（去重、权限、审计）。"""

    # ================ 列表 ================

    async def list_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        *,
        user: "User",
        page: int = 1,
        page_size: int = 20,
        invoice_type: str | None = None,
        search: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        status_filter: str | None = "active",
    ) -> tuple[list["Invoice"], int]:
        """列出当前租户可见的发票（员工仅看自己）。"""
        from app.models import Invoice

        page = max(1, page)
        page_size = min(100, max(1, page_size))

        conditions = [Invoice.tenant_id == tenant_id]
        if status_filter:
            conditions.append(Invoice.status == status_filter)
        else:
            conditions.append(Invoice.status != "deleted")

        # 行级权限：员工仅看自己
        if user.role == "employee":
            conditions.append(Invoice.user_id == user.id)

        # 筛选
        if invoice_type:
            conditions.append(Invoice.invoice_type == invoice_type)
        if search:
            like = f"%{search}%"
            conditions.append(
                or_(
                    Invoice.invoice_title.ilike(like),
                    Invoice.company.ilike(like),
                    Invoice.invoice_number.ilike(like),
                    Invoice.seller.ilike(like),
                    Invoice.buyer.ilike(like),
                )
            )
        if start_date:
            conditions.append(Invoice.invoice_date >= start_date)
        if end_date:
            conditions.append(Invoice.invoice_date <= end_date)

        where = and_(*conditions)

        # 计数
        count_stmt = select(func.count()).select_from(Invoice).where(where)
        total = (await db.execute(count_stmt)).scalar_one()

        # 分页
        offset = (page - 1) * page_size
        stmt = (
            select(Invoice)
            .where(where)
            .order_by(Invoice.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), int(total)

    # ================ 详情 ================

    async def get(
        self, db: AsyncSession, tenant_id: UUID, invoice_id: UUID, *, user: "User | None" = None
    ) -> "Invoice":
        """获取发票详情；权限不足或不存在抛 NotFound/Forbidden。"""
        from app.models import Invoice

        inv = await db.get(Invoice, invoice_id)
        if not inv or inv.tenant_id != tenant_id or inv.status == "deleted":
            raise NotFoundError("发票不存在")
        if user and user.role == "employee" and inv.user_id != user.id:
            raise ForbiddenError("无权查看该发票")
        return inv

    # ================ 按哈希查询（前端轮询） ================

    async def get_by_hash(
        self, db: AsyncSession, tenant_id: UUID, file_hash: str
    ) -> "Invoice | None":
        """前端轮询用：按 file_hash 查最近一张 pending_review 发票。"""
        from app.models import Invoice

        stmt = (
            select(Invoice)
            .where(
                Invoice.tenant_id == tenant_id,
                Invoice.file_hash == file_hash,
                Invoice.status != "deleted",
            )
            .order_by(Invoice.created_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalars().first()

    # ================ OCR 完成后写入 pending_review ================

    async def create_pending(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        file_url: str,
        file_hash: str,
        invoice_title: str | None = None,
        company: str | None = None,
        tax_id: str | None = None,
        invoice_code: str | None = None,
        invoice_number: str | None = None,
        invoice_date: date | None = None,
        amount_excl_tax: Decimal | float | None = None,
        tax_amount: Decimal | float | None = None,
        amount_incl_tax: Decimal | float | None = None,
        invoice_type: str | None = None,
        seller: str | None = None,
        buyer: str | None = None,
        confidence: dict[str, float] | None = None,
    ) -> "Invoice":
        """识别完成后写入待归档。不在这里做归档去重。"""
        from app.models import Invoice

        values = dict(
            tenant_id=tenant_id,
            user_id=user_id,
            invoice_title=invoice_title,
            company=company,
            tax_id=tax_id,
            invoice_code=invoice_code,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount_excl_tax=amount_excl_tax,
            tax_amount=tax_amount,
            amount_incl_tax=amount_incl_tax,
            invoice_type=invoice_type,
            seller=seller,
            buyer=buyer,
            file_url=file_url,
            file_hash=file_hash,
            ocr_confidence=confidence,
            status="pending_review",
        )
        inv = Invoice(**values)
        try:
            db.add(inv)
            await db.flush()
            await db.refresh(inv)
        except IntegrityError:
            # 旧唯一约束会把「待归档」也算重复。未确认的记录更新识别结果，仍保持待归档。
            await db.rollback()
            if not invoice_code or not invoice_number:
                raise
            existing = await self._find_pending_duplicate(
                db, tenant_id, invoice_code, invoice_number
            )
            if existing is None:
                raise
            for key, value in values.items():
                if key in {"tenant_id", "user_id", "status"}:
                    continue
                setattr(existing, key, value)
            existing.status = "pending_review"
            await db.flush()
            await db.refresh(existing)
            logger.info(
                "Invoice recognition refreshed (still pending): id=%s code=%s number=%s",
                existing.id, invoice_code, invoice_number,
            )
            return existing
        logger.info(
            "Invoice created pending: id=%s tenant=%s code=%s number=%s",
            inv.id, tenant_id, invoice_code, invoice_number,
        )
        return inv

    async def _find_pending_duplicate(
        self, db: AsyncSession, tenant_id: UUID, code: str, number: str
    ) -> "Invoice | None":
        """找同一代码+号码、尚未人工确认的发票。"""
        from app.models import Invoice

        stmt = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.invoice_code == code,
            Invoice.invoice_number == number,
            Invoice.status == "pending_review",
        )
        return (await db.execute(stmt)).scalars().first()

    async def _find_archived_duplicate(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        code: str,
        number: str,
        *,
        exclude_id: UUID | None = None,
    ) -> "Invoice | None":
        """只在已归档（active）记录里查重。待归档不参与。"""
        from app.models import Invoice

        stmt = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.invoice_code == code,
            Invoice.invoice_number == number,
            Invoice.status == "active",
        )
        if exclude_id is not None:
            stmt = stmt.where(Invoice.id != exclude_id)
        return (await db.execute(stmt)).scalars().first()

    # ================ 兼容旧 /invoices/archive 接口（直接 JSON 入库） ================

    async def archive(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID,
        invoice_data: dict[str, Any],
    ) -> "Invoice":
        """手动归档入口（Phase A 主路径走 chat_stream + confirm，此方法保留兼容）。"""
        return await self.create_pending(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            file_url=invoice_data.get("file_url", ""),
            file_hash=invoice_data.get("file_hash", ""),
            invoice_title=invoice_data.get("invoice_title"),
            company=invoice_data.get("company"),
            tax_id=invoice_data.get("tax_id"),
            invoice_code=invoice_data.get("invoice_code"),
            invoice_number=invoice_data.get("invoice_number"),
            invoice_date=invoice_data.get("invoice_date"),
            amount_excl_tax=invoice_data.get("amount_excl_tax"),
            tax_amount=invoice_data.get("tax_amount"),
            amount_incl_tax=invoice_data.get("amount_incl_tax"),
            invoice_type=invoice_data.get("invoice_type"),
            seller=invoice_data.get("seller"),
            buyer=invoice_data.get("buyer"),
        )

    # ================ 编辑字段（不改状态） ================

    async def update_fields(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        invoice_id: UUID,
        fields: dict[str, Any],
    ) -> "Invoice":
        inv = await self.get(db, tenant_id, invoice_id, user=user)
        before = _serialize_snapshot(inv)

        editable = {
            "invoice_title", "company", "tax_id",
            "invoice_code", "invoice_number", "invoice_date",
            "amount_excl_tax", "tax_amount", "amount_incl_tax",
            "invoice_type", "seller", "buyer", "remark",
        }
        for k, v in fields.items():
            if k in editable:
                setattr(inv, k, v)

        await db.flush()
        await db.refresh(inv)

        await write_audit_log(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            operation_type="update_invoice",
            target_type="invoice",
            target_id=inv.id,
            before=before,
            after=_serialize_snapshot(inv),
        )
        await db.commit()
        return inv

    # ================ 确认归档（pending → active） ================

    async def confirm(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        invoice_id: UUID,
        fields: dict[str, Any] | None = None,
    ) -> "Invoice":
        inv = await self.get(db, tenant_id, invoice_id, user=user)
        if inv.status == "active":
            raise ConflictError("发票已归档，无需重复确认", code="ALREADY_CONFIRMED")
        if inv.status == "deleted":
            raise NotFoundError("发票不存在")

        before = _serialize_snapshot(inv)

        # 最后一次字段更新
        if fields:
            editable = {
                "invoice_title", "company", "tax_id",
                "invoice_code", "invoice_number", "invoice_date",
                "amount_excl_tax", "tax_amount", "amount_incl_tax",
                "invoice_type", "seller", "buyer", "remark",
            }
            for k, v in fields.items():
                if k in editable:
                    setattr(inv, k, v)

        # 归档去重只发生在确认这一步，识别成功与否不受影响
        if inv.invoice_code and inv.invoice_number:
            dup = await self._find_archived_duplicate(
                db,
                tenant_id,
                inv.invoice_code,
                inv.invoice_number,
                exclude_id=inv.id,
            )
            if dup is not None:
                raise ConflictError(
                    f"归档失败：发票 ({inv.invoice_code}/{inv.invoice_number}) 已在档案中",
                    code="INVOICE_DUPLICATE",
                )

        inv.status = "active"
        await db.flush()
        await db.refresh(inv)

        await write_audit_log(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            operation_type="confirm_invoice",
            target_type="invoice",
            target_id=inv.id,
            before=before,
            after=_serialize_snapshot(inv),
        )
        await db.commit()
        return inv

    # ================ 软删 ================

    async def soft_delete(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        invoice_id: UUID,
    ) -> None:
        inv = await self.get(db, tenant_id, invoice_id, user=user)
        # 财务/管理员可删任何；员工只能删自己
        if user.role == "employee" and inv.user_id != user.id:
            raise ForbiddenError("无权删除该发票")

        before = _serialize_snapshot(inv)
        inv.status = "deleted"
        await db.flush()

        await write_audit_log(
            db,
            tenant_id=tenant_id,
            user_id=user.id,
            operation_type="delete_invoice",
            target_type="invoice",
            target_id=inv.id,
            before=before,
            after={"status": "deleted"},
        )
        await db.commit()

    # ================ 下载（MinIO 预签名 URL） ================

    async def get_presigned_download_url(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID,
        user: "User",
        invoice_id: UUID,
        expires_seconds: int = 3600,
    ) -> str:
        from app.config import settings

        inv = await self.get(db, tenant_id, invoice_id, user=user)
        if not inv.file_url:
            raise NotFoundError("发票原件未上传")

        # file_url 格式 s3://bucket/key
        if not inv.file_url.startswith("s3://"):
            # 兼容直接存的相对路径
            return storage_service.get_presigned_url(
                settings.minio_bucket_invoice, inv.file_url, expires=expires_seconds
            )
        _, _, rest = inv.file_url.partition("s3://")
        bucket, _, key = rest.partition("/")
        return storage_service.get_presigned_url(bucket, key, expires=expires_seconds)


def _serialize_snapshot(inv: "Invoice") -> dict[str, Any]:
    """序列化快照（用于审计日志 before/after）。"""
    return {
        "id": str(inv.id),
        "status": inv.status,
        "invoice_code": inv.invoice_code,
        "invoice_number": inv.invoice_number,
        "amount_incl_tax": float(inv.amount_incl_tax) if inv.amount_incl_tax is not None else None,
    }


invoice_service = InvoiceService()