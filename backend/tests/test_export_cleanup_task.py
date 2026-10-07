"""过期导出清理任务（mock delete_file）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.models import ExportJob, User
from app.tasks.export_cleanup_task import _cleanup_expired_exports


async def _admin_user(db_session) -> User:
    user = (
        await db_session.execute(select(User).where(User.account == "admin"))
    ).scalars().first()
    assert user is not None
    return user


@pytest.mark.asyncio
async def test_cleanup_expired_exports_marks_job_and_deletes(db_session, monkeypatch):
    """过期 succeeded 任务应 delete_file 并置 expired。"""
    user = await _admin_user(db_session)
    job_id = uuid4()
    object_key = f"{user.tenant_id}/exports/{user.id}/{job_id}.xlsx"
    file_url = f"s3://{settings.minio_bucket_exports}/{object_key}"
    deleted: list[tuple[str, str]] = []

    def fake_delete(bucket: str, object_name: str) -> None:
        deleted.append((bucket, object_name))

    monkeypatch.setattr(
        "app.tasks.export_cleanup_task.storage_service.delete_file",
        fake_delete,
    )

    past = datetime.now(timezone.utc) - timedelta(days=1)
    job = ExportJob(
        id=job_id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        resource_type="invoice",
        artifact_kind="xlsx",
        filters={"status_filter": "active"},
        fingerprint=uuid4().hex,
        status="succeeded",
        file_url=file_url,
        file_name="invoices-test.xlsx",
        row_count=1,
        expires_at=past,
        finished_at=past,
    )
    db_session.add(job)
    await db_session.commit()

    try:
        result = await _cleanup_expired_exports()
        assert result["expired"] == 1
        assert result["deleted_objects"] == 1
        assert deleted == [(settings.minio_bucket_exports, object_key)]

        await db_session.expire_all()
        refreshed = await db_session.get(ExportJob, job_id)
        assert refreshed is not None
        assert refreshed.status == "expired"
    finally:
        await db_session.execute(delete(ExportJob).where(ExportJob.id == job_id))
        await db_session.commit()
