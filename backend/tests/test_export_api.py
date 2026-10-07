"""导出服务层 + REST API 测试：创建幂等 / 列表 / 限流 / download / retry。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessError, NotFoundError
from app.models import AuditLog, ExportJob, User
from app.services import export_service


async def _admin_user(db_session) -> User:
    """取种子管理员作为测试用户。"""
    user = (
        await db_session.execute(select(User).where(User.account == "admin"))
    ).scalars().first()
    assert user is not None
    return user


async def _cleanup_jobs(db_session, job_ids: list) -> None:
    """清理本用例创建的导出任务与相关审计。"""
    if not job_ids:
        return
    await db_session.execute(
        delete(AuditLog).where(
            AuditLog.target_type == "export_job",
            AuditLog.target_id.in_(job_ids),
        )
    )
    await db_session.execute(delete(ExportJob).where(ExportJob.id.in_(job_ids)))
    await db_session.commit()


async def _purge_user_inflight(db_session, user: User) -> None:
    """清理用户名下进行中任务，避免脏数据干扰限流/幂等断言。"""
    result = await db_session.execute(
        select(ExportJob.id).where(
            ExportJob.user_id == user.id,
            ExportJob.status.in_(("queued", "running")),
        )
    )
    await _cleanup_jobs(db_session, list(result.scalars().all()))


@pytest.mark.asyncio
async def test_create_job_dedupes(db_session):
    """同 fingerprint 进行中任务应幂等返回，不新建。"""
    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)
    job_ids: list = []
    filters = {"status_filter": "active", "search": f"dedupe-{uuid4().hex}"}
    try:
        job1, d1 = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters=filters,
        )
        await db_session.commit()
        job_ids.append(job1.id)

        job2, d2 = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters=filters,
        )
        assert d1 is False and d2 is True and job1.id == job2.id

        audits = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.operation_type == "export.create",
                    AuditLog.target_id == job1.id,
                )
            )
        ).scalars().all()
        assert len(audits) == 1
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_create_job_dedup_after_integrity_error_commit_ok(db_session, monkeypatch):
    """UniqueViolation 幂等返回后须 expunge 失败 pending，caller commit 不二次 INSERT。"""
    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)
    job_ids: list = []
    filters = {"status_filter": "active", "search": f"ie-{uuid4().hex}"}
    try:
        job1, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters=filters,
        )
        await db_session.commit()
        job_ids.append(job1.id)

        real_flush = db_session.flush
        ie_raised = False

        async def flush_raise_once_then_real(*args, **kwargs):
            nonlocal ie_raised
            if not ie_raised:
                ie_raised = True
                raise IntegrityError("INSERT export_jobs", {}, Exception("unique"))
            return await real_flush(*args, **kwargs)

        monkeypatch.setattr(db_session, "flush", flush_raise_once_then_real)

        job2, d2 = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters=filters,
        )
        assert d2 is True and job2.id == job1.id
        await db_session.commit()

        inflight_count = (
            await db_session.execute(
                select(func.count())
                .select_from(ExportJob)
                .where(
                    ExportJob.user_id == test_user.id,
                    ExportJob.fingerprint == job1.fingerprint,
                    ExportJob.status.in_(("queued", "running")),
                )
            )
        ).scalar_one()
        assert inflight_count == 1
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_create_job_inflight_limit(db_session, monkeypatch):
    """进行中任务数达到上限时抛 EXPORT_INFLIGHT_LIMIT。"""
    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)
    monkeypatch.setattr(settings, "export_max_inflight_per_user", 2)
    job_ids: list = []
    try:
        for i in range(2):
            job, deduped = await export_service.create_export_job(
                db_session,
                test_user,
                resource_type="invoice",
                filters={"status_filter": "active", "search": f"limit-{i}-{uuid4().hex[:8]}"},
            )
            assert deduped is False
            await db_session.commit()
            job_ids.append(job.id)

        with pytest.raises(BusinessError) as exc_info:
            await export_service.create_export_job(
                db_session,
                test_user,
                resource_type="contract",
                filters={"search": f"over-{uuid4().hex[:8]}"},
            )
        assert exc_info.value.code == "EXPORT_INFLIGHT_LIMIT"
        assert exc_info.value.http_status == 429
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_list_and_get_export_jobs(db_session):
    """列表分页与 get 详情；他人任务不可见。"""
    test_user = await _admin_user(db_session)
    job_ids: list = []
    try:
        inv, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters={"status_filter": "all", "search": f"list-{uuid4().hex[:8]}"},
        )
        await db_session.commit()
        job_ids.append(inv.id)
        assert inv.artifact_kind == "xlsx"
        # status_filter=all 原样存入 filters
        assert inv.filters.get("status_filter") == "all"

        con, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="contract",
            filters={"search": f"list-{uuid4().hex[:8]}"},
        )
        await db_session.commit()
        job_ids.append(con.id)
        assert con.artifact_kind == "zip"

        items, total = await export_service.list_export_jobs(
            db_session, test_user, resource_type="invoice", page=1, page_size=20
        )
        assert total >= 1
        assert all(j.resource_type == "invoice" for j in items)
        assert any(j.id == inv.id for j in items)

        got = await export_service.get_export_job(db_session, test_user, inv.id)
        assert got.id == inv.id

        with pytest.raises(NotFoundError) as exc_info:
            await export_service.get_export_job(db_session, test_user, uuid4())
        assert exc_info.value.code == "EXPORT_NOT_FOUND"
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_terminal_job_allows_recreate(db_session):
    """终态任务不阻挡相同 filters 再次创建。"""
    test_user = await _admin_user(db_session)
    job_ids: list = []
    filters = {"status_filter": "active", "search": f"term-{uuid4().hex[:8]}"}
    try:
        job1, d1 = await export_service.create_export_job(
            db_session, test_user, resource_type="invoice", filters=filters
        )
        await db_session.commit()
        job_ids.append(job1.id)
        assert d1 is False

        job1.status = "succeeded"
        await db_session.commit()

        job2, d2 = await export_service.create_export_job(
            db_session, test_user, resource_type="invoice", filters=filters
        )
        await db_session.commit()
        job_ids.append(job2.id)
        assert d2 is False
        assert job2.id != job1.id
    finally:
        await _cleanup_jobs(db_session, job_ids)


# ---------------------------------------------------------------------------
# HTTP：REST /api/v1/exports（monkeypatch Celery delay）
# ---------------------------------------------------------------------------


def _stub_export_delay(monkeypatch) -> list[str]:
    """将 export_artifact.delay 置空，记录入队 job_id。"""
    enqueued: list[str] = []

    def _fake_delay(job_id: str, *args, **kwargs):
        enqueued.append(job_id)
        return None

    monkeypatch.setattr(
        "app.tasks.export_task.export_artifact.delay",
        _fake_delay,
    )
    # 路由模块可能已绑定同名引用
    monkeypatch.setattr(
        "app.api.v1.exports.export_artifact.delay",
        _fake_delay,
    )
    return enqueued


@pytest.mark.asyncio
async def test_http_create_commits_before_celery_delay(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """POST 须先 commit 再 delay，避免 Worker 读不到 queued 行。"""
    order: list[str] = []
    real_commit = AsyncSession.commit

    async def commit_wrapper(self, *args, **kwargs):
        order.append("commit")
        return await real_commit(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "commit", commit_wrapper)

    def _fake_delay(job_id: str, *args, **kwargs):
        order.append("delay")
        return None

    monkeypatch.setattr(
        "app.tasks.export_task.export_artifact.delay",
        _fake_delay,
    )
    monkeypatch.setattr(
        "app.api.v1.exports.export_artifact.delay",
        _fake_delay,
    )

    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)
    body = {
        "resource_type": "invoice",
        "filters": {"status_filter": "active", "search": f"commit-first-{uuid4().hex[:8]}"},
    }
    job_ids: list = []
    try:
        r = await client.post("/api/v1/exports/", json=body, headers=auth_headers)
        assert r.status_code == 200, r.text
        job_ids.append(UUID(r.json()["id"]))
        assert "commit" in order
        assert "delay" in order
        assert order.index("commit") < order.index("delay")
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_http_create_export_dedupes_inflight(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """POST 同 filters 第二次应 deduplicated，且只入队一次。"""
    enqueued = _stub_export_delay(monkeypatch)
    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)
    body = {
        "resource_type": "invoice",
        "filters": {"status_filter": "active", "search": f"http-dedupe-{uuid4().hex[:8]}"},
    }
    job_ids: list = []
    try:
        r1 = await client.post("/api/v1/exports/", json=body, headers=auth_headers)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1["deduplicated"] is False
        assert j1["status"] == "queued"
        job_ids.append(UUID(j1["id"]))

        r2 = await client.post("/api/v1/exports/", json=body, headers=auth_headers)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2["deduplicated"] is True
        assert j2["id"] == j1["id"]
        assert j2.get("message") == "已有相同导出任务"
        assert enqueued == [j1["id"]]
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_download_rejects_non_succeeded(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """queued 任务不可下载。"""
    _stub_export_delay(monkeypatch)
    body = {
        "resource_type": "invoice",
        "filters": {"status_filter": "active", "search": f"dl-rej-{uuid4().hex[:8]}"},
    }
    job_ids: list = []
    try:
        r = await client.post("/api/v1/exports/", json=body, headers=auth_headers)
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        job_ids.append(UUID(job_id))

        r2 = await client.get(
            f"/api/v1/exports/{job_id}/download", headers=auth_headers
        )
        assert r2.status_code == 400
        assert r2.json()["code"] == "EXPORT_NOT_DOWNLOADABLE"
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_download_succeeded_returns_presign(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """succeeded + 合法 s3 地址应返回预签名 URL，并写 export.download 审计。"""
    _stub_export_delay(monkeypatch)
    monkeypatch.setattr(
        "app.services.export_service.storage_service.get_presigned_url",
        lambda bucket, key, expires=600: f"https://presign.test/{bucket}/{key}?e={expires}",
    )
    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)
    job_ids: list = []
    try:
        job, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters={"status_filter": "active", "search": f"dl-ok-{uuid4().hex[:8]}"},
        )
        await db_session.commit()
        job_ids.append(job.id)

        job.status = "succeeded"
        job.file_url = (
            f"s3://{settings.minio_bucket_exports}/"
            f"{test_user.tenant_id}/exports/{test_user.id}/{job.id}.xlsx"
        )
        job.file_name = "invoices-20261007-1200.xlsx"
        job.row_count = 1
        await db_session.commit()

        r = await client.get(
            f"/api/v1/exports/{job.id}/download", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["expires_in"] == 600
        assert data["url"].startswith("https://presign.test/")

        audits = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.operation_type == "export.download",
                    AuditLog.target_id == job.id,
                )
            )
        ).scalars().all()
        assert len(audits) >= 1
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_retry_only_failed(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """仅 failed 可 retry；queued 拒绝；failed 后新建并入队。"""
    enqueued = _stub_export_delay(monkeypatch)
    body = {
        "resource_type": "invoice",
        "filters": {"status_filter": "active", "search": f"retry-{uuid4().hex[:8]}"},
    }
    job_ids: list = []
    try:
        r = await client.post("/api/v1/exports/", json=body, headers=auth_headers)
        assert r.status_code == 200, r.text
        job_id = UUID(r.json()["id"])
        job_ids.append(job_id)

        r_bad = await client.post(
            f"/api/v1/exports/{job_id}/retry", headers=auth_headers
        )
        assert r_bad.status_code == 400
        assert r_bad.json()["code"] == "EXPORT_RETRY_NOT_ALLOWED"

        job = await db_session.get(ExportJob, job_id)
        assert job is not None
        job.status = "failed"
        job.error_message = "模拟失败"
        await db_session.commit()

        r_ok = await client.post(
            f"/api/v1/exports/{job_id}/retry", headers=auth_headers
        )
        assert r_ok.status_code == 200, r_ok.text
        j2 = r_ok.json()
        assert j2["deduplicated"] is False
        assert j2["status"] == "queued"
        assert j2["id"] != str(job_id)
        job_ids.append(UUID(j2["id"]))
        assert j2["id"] in enqueued
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_employee_cannot_download_others_job(
    client: AsyncClient,
    auth_headers,
    employee_headers,
    db_session,
    monkeypatch,
):
    """员工不可下载他人导出任务（行级隔离 → 404）。"""
    _stub_export_delay(monkeypatch)
    monkeypatch.setattr(
        "app.services.export_service.storage_service.get_presigned_url",
        lambda *a, **k: "https://presign.test/x",
    )
    test_user = await _admin_user(db_session)
    job_ids: list = []
    try:
        job, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters={"status_filter": "active", "search": f"emp-dl-{uuid4().hex[:8]}"},
        )
        await db_session.commit()
        job_ids.append(job.id)
        job.status = "succeeded"
        job.file_url = (
            f"s3://{settings.minio_bucket_exports}/"
            f"{test_user.tenant_id}/exports/{test_user.id}/{job.id}.xlsx"
        )
        job.file_name = "x.xlsx"
        job.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        await db_session.commit()

        r = await client.get(
            f"/api/v1/exports/{job.id}/download", headers=employee_headers
        )
        assert r.status_code == 404
        assert r.json()["code"] in ("EXPORT_NOT_FOUND", "NOT_FOUND")
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_download_rejects_expired(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """已过期 succeeded 任务不可下载。"""
    _stub_export_delay(monkeypatch)
    test_user = await _admin_user(db_session)
    job_ids: list = []
    try:
        job, _ = await export_service.create_export_job(
            db_session,
            test_user,
            resource_type="invoice",
            filters={"status_filter": "active", "search": f"exp-{uuid4().hex[:8]}"},
        )
        await db_session.commit()
        job_ids.append(job.id)
        job.status = "succeeded"
        job.file_url = (
            f"s3://{settings.minio_bucket_exports}/"
            f"{test_user.tenant_id}/exports/{test_user.id}/{job.id}.xlsx"
        )
        job.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()

        r = await client.get(
            f"/api/v1/exports/{job.id}/download", headers=auth_headers
        )
        assert r.status_code == 400
        assert r.json()["code"] == "EXPORT_NOT_DOWNLOADABLE"
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_http_create_marks_failed_when_delay_raises(
    client: AsyncClient, auth_headers, db_session, monkeypatch
):
    """commit 后 delay 抛错 → job 标 failed，不永久占 queued 幂等槽。"""
    test_user = await _admin_user(db_session)
    await _purge_user_inflight(db_session, test_user)

    def _boom(job_id: str, *args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(
        "app.tasks.export_task.export_artifact.delay",
        _boom,
    )
    monkeypatch.setattr(
        "app.api.v1.exports.export_artifact.delay",
        _boom,
    )

    body = {
        "resource_type": "invoice",
        "filters": {
            "status_filter": "active",
            "search": f"enqueue-fail-{uuid4().hex[:8]}",
        },
    }
    job_ids: list = []
    try:
        r = await client.post("/api/v1/exports/", json=body, headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        job_ids.append(UUID(data["id"]))
        assert data["status"] == "failed"
        assert data["error_message"] == "导出任务入队失败，请重试"
        assert data["deduplicated"] is False

        await db_session.expire_all()
        row = await db_session.get(ExportJob, job_ids[0])
        assert row is not None
        assert row.status == "failed"
        assert row.error_message == "导出任务入队失败，请重试"

        failed_audits = (
            await db_session.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.target_type == "export_job",
                    AuditLog.target_id == job_ids[0],
                    AuditLog.operation_type == "export.failed",
                )
            )
        ).scalar_one()
        assert int(failed_audits) >= 1
    finally:
        await _cleanup_jobs(db_session, job_ids)


@pytest.mark.asyncio
async def test_files_presign_rejects_exports_bucket(
    client: AsyncClient, auth_headers, db_session
):
    """/files/presign 不得签发 exports 桶；下载须走 /exports/{id}/download。"""
    test_user = await _admin_user(db_session)
    file_url = (
        f"s3://{settings.minio_bucket_exports}/"
        f"{test_user.tenant_id}/exports/{test_user.id}/{uuid4()}.xlsx"
    )
    r = await client.get(
        "/api/v1/files/presign",
        params={"file_url": file_url},
        headers=auth_headers,
    )
    assert r.status_code == 403
    assert r.json()["code"] == "FILE_FORBIDDEN"
