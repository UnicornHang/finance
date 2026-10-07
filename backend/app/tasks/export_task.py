"""异步导出 Celery 任务：按 ExportJob 生成发票 xlsx / 合同报告 zip 并上传 MinIO。

流程与 ocr_task 一致：同步 Celery 入口 + asyncio.run + async_session_factory。
入队由 API 层调用 export_artifact.delay；本模块不挂 REST。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import settings
from app.core.database import async_session_factory
from app.models import Contract, ExportJob, Invoice, User
from app.services import export_service
from app.services.contract_service import contract_service
from app.services.export_contract_pdf import (
    ContractView,
    ViolationItem,
    build_contract_report_pdf,
    build_contract_reports_zip,
    safe_pdf_filename,
)
from app.services.export_invoice_xlsx import InvoiceRow, build_invoice_xlsx
from app.services.invoice_service import invoice_service
from app.services.storage_service import storage_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 与前端 invoiceMeta TYPE_LABEL / STATUS_LABEL 对齐
_INVOICE_TYPE_LABEL: dict[str, str] = {
    "special": "专票",
    "general": "普票",
    "electronic": "电子发票",
    "vehicle": "机动车销售发票",
}
_INVOICE_STATUS_LABEL: dict[str, str] = {
    "pending_review": "待确认",
    "active": "已归档",
    "deleted": "已删除",
}

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_ZIP_CONTENT_TYPE = "application/zip"
_PAGE_SIZE = 100


def _shanghai_ts() -> str:
    """Asia/Shanghai 时间戳，用于下载文件名。"""
    return datetime.now(_TZ_SHANGHAI).strftime("%Y%m%d-%H%M")


def _fmt_local_dt(value: datetime | None) -> str | None:
    """归档时间本地化：YYYY/MM/DD HH:mm（对齐前端 formatDate 观感）。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(_TZ_SHANGHAI).strftime("%Y/%m/%d %H:%M")


def _fmt_date(value: date | datetime | None) -> str | None:
    """日期字段格式化为 YYYY-MM-DD。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _parse_filter_date(value: Any) -> date | None:
    """解析 filters 中的日期；无效则忽略。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _object_key(job: ExportJob, ext: str) -> str:
    """MinIO 对象键：{tenant}/exports/{user}/{job}.{ext}。"""
    return f"{job.tenant_id}/exports/{job.user_id}/{job.id}.{ext}"


async def _page_invoices(
    db,
    *,
    user: User,
    invoice_type: str | None,
    search: str | None,
    status_filter: str | None,
    start_date: date | None,
    end_date: date | None,
) -> list[Invoice]:
    """按 page_size=100 翻页拉全量发票。"""
    collected: list[Invoice] = []
    page = 1
    while True:
        rows, total = await invoice_service.list_by_tenant(
            db,
            user.tenant_id,
            user=user,
            page=page,
            page_size=_PAGE_SIZE,
            invoice_type=invoice_type,
            search=search,
            start_date=start_date,
            end_date=end_date,
            status_filter=status_filter,
        )
        collected.extend(rows)
        if not rows or len(collected) >= total:
            break
        page += 1
    return collected


async def _load_invoices_for_job(db, user: User, filters: dict[str, Any]) -> list[Invoice]:
    """按 job.filters 加载导出发票；status_filter=all 仅 pending_review+active。"""
    raw = dict(filters or {})
    invoice_type = raw.get("invoice_type") or None
    search = (raw.get("search") or "").strip() or None
    status_filter = raw.get("status_filter") or "active"
    start_date = _parse_filter_date(raw.get("start_date"))
    end_date = _parse_filter_date(raw.get("end_date"))

    if status_filter == "all":
        # list API 的 all 含 deleted；导出只要待确认+已归档
        pending = await _page_invoices(
            db,
            user=user,
            invoice_type=invoice_type,
            search=search,
            status_filter="pending_review",
            start_date=start_date,
            end_date=end_date,
        )
        active = await _page_invoices(
            db,
            user=user,
            invoice_type=invoice_type,
            search=search,
            status_filter="active",
            start_date=start_date,
            end_date=end_date,
        )
        merged = {inv.id: inv for inv in pending + active}
        return sorted(
            merged.values(),
            key=lambda inv: inv.created_at or datetime.min.replace(tzinfo=ZoneInfo("UTC")),
            reverse=True,
        )

    return await _page_invoices(
        db,
        user=user,
        invoice_type=invoice_type,
        search=search,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date,
    )


async def _operator_names(db, user_ids: set[UUID]) -> dict[UUID, str]:
    """批量查操作用户姓名。"""
    if not user_ids:
        return {}
    rows = (
        await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
    ).all()
    return {uid: name for uid, name in rows}


def _invoice_to_row(inv: Invoice, operator_name: str | None) -> InvoiceRow:
    """Invoice ORM → 导出行（中文类型/状态 + 本地化时间）。"""
    itype = inv.invoice_type or ""
    return InvoiceRow(
        invoice_title=inv.invoice_title,
        company=inv.company,
        tax_id=inv.tax_id,
        invoice_code=inv.invoice_code,
        invoice_number=inv.invoice_number,
        invoice_date=_fmt_date(inv.invoice_date),
        amount_excl_tax=inv.amount_excl_tax,
        tax_amount=inv.tax_amount,
        amount_incl_tax=inv.amount_incl_tax,
        invoice_type_label=_INVOICE_TYPE_LABEL.get(itype, itype or None),
        seller=inv.seller,
        buyer=inv.buyer,
        remark=inv.remark,
        status_label=_INVOICE_STATUS_LABEL.get(inv.status, inv.status),
        operator_name=operator_name,
        created_at_label=_fmt_local_dt(inv.created_at),
    )


async def _build_invoice_artifact(
    db, user: User, job: ExportJob
) -> tuple[bytes, str, str, int]:
    """生成发票 xlsx；(bytes, content_type, file_name, row_count)。"""
    invoices = await _load_invoices_for_job(db, user, job.filters or {})
    names = await _operator_names(db, {inv.user_id for inv in invoices})
    rows = [_invoice_to_row(inv, names.get(inv.user_id)) for inv in invoices]
    data = build_invoice_xlsx(rows)
    file_name = f"invoices-{_shanghai_ts()}.xlsx"
    return data, _XLSX_CONTENT_TYPE, file_name, len(rows)


def _contract_view(contract, exported_at: str) -> ContractView:
    """Contract ORM → PDF 视图；无审查结果时摘要/违规留空由生成器填默认文案。"""
    result = contract.review_result if isinstance(contract.review_result, dict) else {}
    summary = result.get("summary")
    if summary is not None and not isinstance(summary, str):
        summary = str(summary)
    raw_violations = result.get("violations") or []
    violations: list[ViolationItem] = []
    for item in raw_violations:
        if not isinstance(item, dict):
            continue
        violations.append(
            ViolationItem(
                clause=item.get("clause"),
                issue=item.get("issue"),
                severity=item.get("severity"),
            )
        )
    return ContractView(
        contract_name=contract.contract_name,
        contract_no=contract.contract_no,
        party_a=contract.party_a,
        party_b=contract.party_b,
        sign_date=_fmt_date(contract.sign_date),
        effective_start=_fmt_date(contract.effective_start),
        amount=contract.amount,
        risk_level=contract.risk_level,
        status=contract.status,
        exported_at=exported_at,
        summary=summary,
        violations=tuple(violations),
    )


async def _page_contracts(
    db,
    *,
    user: User,
    search: str | None,
    risk_level: str | None,
) -> list[Contract]:
    """按 page_size 翻页拉全量合同（排除 deleted；不走 list_by_tenant 的 200 上限）。"""
    collected: list[Contract] = []
    page = 1
    while True:
        rows, total = await contract_service.list_for_export(
            db,
            user.tenant_id,
            user=user,
            search=search,
            risk_level=risk_level,
            page=page,
            page_size=_PAGE_SIZE,
        )
        collected.extend(rows)
        if not rows or len(collected) >= total:
            break
        page += 1
    return collected


async def _build_contract_artifact(
    db, user: User, job: ExportJob
) -> tuple[bytes, str, str, int]:
    """生成合同报告 zip；(bytes, content_type, file_name, row_count)。"""
    raw = dict(job.filters or {})
    search = (raw.get("search") or "").strip() or None
    risk_level = raw.get("risk_level") or None
    contracts = await _page_contracts(
        db, user=user, search=search, risk_level=risk_level
    )
    exported_at = _fmt_local_dt(datetime.now(ZoneInfo("UTC"))) or ""
    zip_items: list[tuple[str, bytes]] = []
    for contract in contracts:
        view = _contract_view(contract, exported_at)
        pdf_bytes = build_contract_report_pdf(view)
        base_name = contract.contract_name or contract.contract_no or "contract"
        short_id = str(contract.id).replace("-", "")[:8]
        zip_items.append((safe_pdf_filename(base_name, short_id), pdf_bytes))
    data = build_contract_reports_zip(zip_items)
    file_name = f"contract-reports-{_shanghai_ts()}.zip"
    return data, _ZIP_CONTENT_TYPE, file_name, len(zip_items)


async def _run_export(job_id: UUID) -> dict[str, Any]:
    """实际执行：加载 job → running → 生成 → 上传 → succeeded/failed。"""
    async with async_session_factory() as db:
        job = await export_service.load_export_job(db, job_id)
        if job is None:
            logger.warning("export_artifact: job not found id=%s", job_id)
            return {"status": "missing", "job_id": str(job_id)}

        if export_service.is_terminal_status(job.status):
            logger.info(
                "export_artifact: skip terminal job id=%s status=%s",
                job_id,
                job.status,
            )
            return {"status": job.status, "job_id": str(job_id), "skipped": True}

        await export_service.mark_export_running(db, job)
        await db.commit()

    try:
        async with async_session_factory() as db:
            job = await export_service.load_export_job(db, job_id)
            if job is None:
                return {"status": "missing", "job_id": str(job_id)}

            user = await db.get(User, job.user_id)
            if user is None:
                raise RuntimeError("导出任务发起人不存在")

            if job.resource_type == "invoice":
                data, content_type, file_name, row_count = await _build_invoice_artifact(
                    db, user, job
                )
                ext = "xlsx"
            elif job.resource_type == "contract":
                data, content_type, file_name, row_count = await _build_contract_artifact(
                    db, user, job
                )
                ext = "zip"
            else:
                raise RuntimeError(f"不支持的导出资源类型：{job.resource_type}")

            object_name = _object_key(job, ext)
            file_url = storage_service.upload_file(
                settings.minio_bucket_exports,
                object_name,
                data,
                content_type=content_type,
            )
            await export_service.mark_export_succeeded(
                db,
                job,
                file_url=file_url,
                file_name=file_name,
                row_count=row_count,
            )
            await db.commit()
            logger.info(
                "export_artifact: succeeded job=%s rows=%s key=%s",
                job_id,
                row_count,
                object_name,
            )
            return {
                "status": "succeeded",
                "job_id": str(job_id),
                "row_count": row_count,
                "file_name": file_name,
            }
    except Exception as exc:
        logger.exception("export_artifact: failed job=%s", job_id)
        # 单独会话写失败态，避免生成阶段脏事务
        async with async_session_factory() as db:
            job = await export_service.load_export_job(db, job_id)
            if job is not None and not export_service.is_terminal_status(job.status):
                await export_service.mark_export_failed(
                    db, job, error_message=str(exc) or "导出失败"
                )
                await db.commit()
        return {
            "status": "failed",
            "job_id": str(job_id),
            "error": str(exc),
        }


@celery_app.task(name="app.tasks.export_task.export_artifact")
def export_artifact(job_id: str) -> dict:
    """Celery 入口：根据 job_id 异步生成导出产物。"""
    return asyncio.run(_run_export(UUID(job_id)))
