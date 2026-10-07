"""Celery export_artifact 任务测试（mock storage；不启 worker）。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.models import AuditLog, Contract, ExportJob, Invoice, User
from app.services import export_service
from app.tasks.export_task import _run_export


async def _admin_user(db_session) -> User:
    """取种子管理员。"""
    user = (
        await db_session.execute(select(User).where(User.account == "admin"))
    ).scalars().first()
    assert user is not None
    return user


async def _cleanup(
    db_session, *, job_ids: list, invoice_ids: list, contract_ids: list | None = None
) -> None:
    """清理本用例任务、审计、发票与合同。"""
    if job_ids:
        await db_session.execute(
            delete(AuditLog).where(
                AuditLog.target_type == "export_job",
                AuditLog.target_id.in_(job_ids),
            )
        )
        await db_session.execute(delete(ExportJob).where(ExportJob.id.in_(job_ids)))
    if invoice_ids:
        await db_session.execute(delete(Invoice).where(Invoice.id.in_(invoice_ids)))
    if contract_ids:
        await db_session.execute(delete(Contract).where(Contract.id.in_(contract_ids)))
    await db_session.commit()


@pytest.mark.asyncio
async def test_export_artifact_invoice_succeeds(db_session, monkeypatch):
    """queued job + 匹配发票 → succeeded，且 storage.upload 被调用。"""
    test_user = await _admin_user(db_session)
    token = uuid4().hex[:12]
    job_ids: list = []
    invoice_ids: list = []
    uploads: list[tuple] = []

    def fake_upload(bucket, object_name, data, content_type="application/octet-stream"):
        """记录上传参数并返回伪 s3 URL。"""
        uploads.append((bucket, object_name, len(data or b""), content_type))
        return f"s3://{bucket}/{object_name}"

    monkeypatch.setattr(
        "app.tasks.export_task.storage_service.upload_file",
        fake_upload,
    )

    try:
        inv = Invoice(
            tenant_id=test_user.tenant_id,
            user_id=test_user.id,
            invoice_title=f"导出测-{token}",
            company=f"导出公司-{token}",
            invoice_code=f"CODE{token}",
            invoice_number=f"NUM{token}",
            status="active",
            invoice_type="general",
        )
        db_session.add(inv)
        await db_session.flush()
        invoice_ids.append(inv.id)

        job, deduped = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters={"status_filter": "active", "search": token},
        )
        assert deduped is False
        await db_session.commit()
        job_ids.append(job.id)

        result = await _run_export(job.id)
        assert result["status"] == "succeeded"
        assert result["row_count"] >= 1
        assert uploads, "storage.upload_file 应被调用"
        assert uploads[0][1].endswith(f"{job.id}.xlsx")

        await db_session.expire_all()
        refreshed = await db_session.get(ExportJob, job.id)
        assert refreshed is not None
        assert refreshed.status == "succeeded"
        assert refreshed.row_count is not None and refreshed.row_count >= 1
        assert refreshed.file_url and refreshed.file_name
        assert refreshed.file_name.startswith("invoices-")
        assert refreshed.file_name.endswith(".xlsx")
    finally:
        await _cleanup(db_session, job_ids=job_ids, invoice_ids=invoice_ids)


@pytest.mark.asyncio
async def test_export_artifact_skips_terminal(db_session, monkeypatch):
    """终态任务重投应立即返回，不上传。"""
    test_user = await _admin_user(db_session)
    job_ids: list = []
    uploads: list = []

    monkeypatch.setattr(
        "app.tasks.export_task.storage_service.upload_file",
        lambda *a, **k: uploads.append(1) or "s3://x/y",
    )

    try:
        job, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters={"status_filter": "active", "search": f"term-{uuid4().hex[:8]}"},
        )
        await db_session.commit()
        job_ids.append(job.id)
        job.status = "succeeded"
        job.row_count = 0
        await db_session.commit()

        result = await _run_export(job.id)
        assert result.get("skipped") is True
        assert result["status"] == "succeeded"
        assert uploads == []
    finally:
        await _cleanup(db_session, job_ids=job_ids, invoice_ids=[])


@pytest.mark.asyncio
async def test_export_artifact_contract_pages_all(db_session, monkeypatch):
    """合同导出翻页拉全；page_size 缩小时仍应全部入 zip（不截断在 200）。"""
    test_user = await _admin_user(db_session)
    token = uuid4().hex[:12]
    job_ids: list = []
    contract_ids: list = []
    uploads: list[tuple] = []

    monkeypatch.setattr("app.tasks.export_task._PAGE_SIZE", 2)

    def fake_upload(bucket, object_name, data, content_type="application/octet-stream"):
        """记录上传参数并返回伪 s3 URL。"""
        uploads.append((bucket, object_name, len(data or b""), content_type))
        return f"s3://{bucket}/{object_name}"

    monkeypatch.setattr(
        "app.tasks.export_task.storage_service.upload_file",
        fake_upload,
    )

    try:
        for i in range(5):
            row = Contract(
                tenant_id=test_user.tenant_id,
                user_id=test_user.id,
                contract_name=f"导出合同-{token}-{i}",
                contract_no=f"C-{token}-{i}",
                status="active",
                risk_level="low",
            )
            db_session.add(row)
            await db_session.flush()
            contract_ids.append(row.id)

        job, deduped = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="contract",
            filters={"search": token},
        )
        assert deduped is False
        await db_session.commit()
        job_ids.append(job.id)

        result = await _run_export(job.id)
        assert result["status"] == "succeeded"
        assert result["row_count"] == 5
        assert uploads, "storage.upload_file 应被调用"
        assert uploads[0][1].endswith(f"{job.id}.zip")

        await db_session.expire_all()
        refreshed = await db_session.get(ExportJob, job.id)
        assert refreshed is not None
        assert refreshed.status == "succeeded"
        assert refreshed.row_count == 5
        assert refreshed.file_name and refreshed.file_name.endswith(".zip")
    finally:
        await _cleanup(
            db_session, job_ids=job_ids, invoice_ids=[], contract_ids=contract_ids
        )
