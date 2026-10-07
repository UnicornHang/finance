"""异步导出任务服务：创建幂等、列表、详情、download、retry。

说明：
- filters 原样写入 JSONB（展示用）；fingerprint 基于规范化结果。
- 发票 filters 中 status_filter 取值同 list API：active / pending_review / all。
  status_filter="all" 原样存储；worker 查数时应排除 deleted（与前端档案一致，不进导出）。
- 入队由 API 层对新建 job 调用 Celery.delay，本模块不耦合任务队列。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.models import ExportJob, User
from app.services.audit_service import write_audit_log
from app.services.export_fingerprint import (
    export_fingerprint,
    normalize_contract_filters,
    normalize_invoice_filters,
)
from app.services.storage_service import parse_s3_url, storage_service

# 进行中状态：参与幂等去重与并发限流
_INFLIGHT_STATUSES = ("queued", "running")

# 终态：Celery 重投时直接跳过
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "expired"})

# 失败文案对用户可见，截断避免堆栈/长文本
_ERROR_MESSAGE_MAX_LEN = 200

# resource_type → 产物类型
_ARTIFACT_KIND_BY_RESOURCE: dict[str, str] = {
    "invoice": "xlsx",
    "contract": "zip",
}

# 下载预签名默认过期（秒）；设计约定约 10 分钟
_DOWNLOAD_PRESIGN_EXPIRES = 600


def is_terminal_status(status: str) -> bool:
    """判断导出任务是否已到终态（succeeded / failed / expired）。"""
    return status in _TERMINAL_STATUSES


def _short_error(message: str) -> str:
    """截断为用户可见短文案。"""
    text = (message or "").strip() or "导出失败"
    if len(text) <= _ERROR_MESSAGE_MAX_LEN:
        return text
    return text[: _ERROR_MESSAGE_MAX_LEN - 1] + "…"


def _parse_optional_date(value: Any) -> date | None:
    """将 filters 中的日期字段解析为 date；空值返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise BusinessError("无效的日期筛选", code="EXPORT_INVALID_FILTERS")


def _normalize_filters(resource_type: str, filters: dict[str, Any] | None) -> dict[str, Any]:
    """按资源类型规范化 filters，供 fingerprint 计算。"""
    raw = dict(filters or {})
    if resource_type == "invoice":
        return normalize_invoice_filters(
            invoice_type=raw.get("invoice_type"),
            search=raw.get("search"),
            status_filter=raw.get("status_filter", "active"),
            start_date=_parse_optional_date(raw.get("start_date")),
            end_date=_parse_optional_date(raw.get("end_date")),
        )
    if resource_type == "contract":
        return normalize_contract_filters(
            search=raw.get("search"),
            risk_level=raw.get("risk_level"),
        )
    raise BusinessError(
        f"不支持的导出资源类型：{resource_type}",
        code="EXPORT_INVALID_RESOURCE",
    )


def _artifact_kind(resource_type: str) -> str:
    """由 resource_type 推导 artifact_kind。"""
    kind = _ARTIFACT_KIND_BY_RESOURCE.get(resource_type)
    if kind is None:
        raise BusinessError(
            f"不支持的导出资源类型：{resource_type}",
            code="EXPORT_INVALID_RESOURCE",
        )
    return kind


async def _find_inflight_by_fingerprint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    fingerprint: str,
) -> ExportJob | None:
    """查找同用户同 fingerprint 的进行中任务。"""
    result = await db.execute(
        select(ExportJob).where(
            ExportJob.tenant_id == tenant_id,
            ExportJob.user_id == user_id,
            ExportJob.fingerprint == fingerprint,
            ExportJob.status.in_(_INFLIGHT_STATUSES),
        )
    )
    return result.scalars().first()


async def _count_inflight(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> int:
    """统计用户当前进行中的导出任务数（发票+合同合计）。"""
    result = await db.execute(
        select(func.count())
        .select_from(ExportJob)
        .where(
            ExportJob.tenant_id == tenant_id,
            ExportJob.user_id == user_id,
            ExportJob.status.in_(_INFLIGHT_STATUSES),
        )
    )
    return int(result.scalar_one())


async def create_export_job(
    db: AsyncSession,
    user: User,
    *,
    resource_type: str,
    filters: dict[str, Any] | None = None,
) -> tuple[ExportJob, bool]:
    """创建导出任务；进行中同 fingerprint 幂等返回。

    返回 (job, deduplicated)。新建时写审计 export.create；幂等命中不写审计、不二次入队。
    """
    normalized = _normalize_filters(resource_type, filters)
    fingerprint = export_fingerprint(normalized)

    existing = await _find_inflight_by_fingerprint(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return existing, True

    inflight = await _count_inflight(
        db, tenant_id=user.tenant_id, user_id=user.id
    )
    if inflight >= settings.export_max_inflight_per_user:
        raise BusinessError(
            f"同时进行中的导出任务已达上限（{settings.export_max_inflight_per_user}）",
            code="EXPORT_INFLIGHT_LIMIT",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    now = datetime.now(timezone.utc)
    # filters 原样存储；status_filter=all 时 worker 须排除 deleted
    stored_filters = dict(filters or {})
    job = ExportJob(
        tenant_id=user.tenant_id,
        user_id=user.id,
        resource_type=resource_type,
        artifact_kind=_artifact_kind(resource_type),
        filters=stored_filters,
        fingerprint=fingerprint,
        status="queued",
        expires_at=now + timedelta(days=settings.export_retention_days),
    )

    try:
        # 并发双插时部分唯一索引冲突：回滚 savepoint 后改返回已有任务
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError:
        existing = await _find_inflight_by_fingerprint(
            db,
            tenant_id=user.tenant_id,
            user_id=user.id,
            fingerprint=fingerprint,
        )
        if existing is not None:
            # savepoint 已回滚 INSERT，但 pending 实例仍在 session.new；须 expunge 以免 caller commit 再次冲突
            db.expunge(job)
            return existing, True
        raise

    await write_audit_log(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        operation_type="export.create",
        target_type="export_job",
        target_id=job.id,
        after={
            "resource_type": job.resource_type,
            "artifact_kind": job.artifact_kind,
            "fingerprint": job.fingerprint,
            "status": job.status,
        },
    )
    await db.refresh(job)
    return job, False


async def list_export_jobs(
    db: AsyncSession,
    user: User,
    *,
    resource_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ExportJob], int]:
    """分页列出当前用户的导出任务，按创建时间倒序。"""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20

    conditions = [
        ExportJob.tenant_id == user.tenant_id,
        ExportJob.user_id == user.id,
    ]
    if resource_type:
        conditions.append(ExportJob.resource_type == resource_type)

    total_result = await db.execute(
        select(func.count()).select_from(ExportJob).where(*conditions)
    )
    total = int(total_result.scalar_one())

    result = await db.execute(
        select(ExportJob)
        .where(*conditions)
        .order_by(ExportJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_export_job(
    db: AsyncSession,
    user: User,
    job_id: UUID,
) -> ExportJob:
    """获取当前用户名下的导出任务详情。"""
    result = await db.execute(
        select(ExportJob).where(
            ExportJob.id == job_id,
            ExportJob.tenant_id == user.tenant_id,
            ExportJob.user_id == user.id,
        )
    )
    job = result.scalars().first()
    if job is None:
        raise NotFoundError("导出任务不存在", code="EXPORT_NOT_FOUND")
    return job


async def load_export_job(db: AsyncSession, job_id: UUID) -> ExportJob | None:
    """Worker：按主键加载导出任务（不校验发起人）。"""
    return await db.get(ExportJob, job_id)


async def mark_export_running(db: AsyncSession, job: ExportJob) -> ExportJob:
    """将任务置为 running，并记录 started_at。"""
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.error_message = None
    await db.flush()
    return job


async def mark_export_succeeded(
    db: AsyncSession,
    job: ExportJob,
    *,
    file_url: str,
    file_name: str,
    row_count: int,
) -> ExportJob:
    """标记成功并写审计 export.succeeded。"""
    now = datetime.now(timezone.utc)
    job.status = "succeeded"
    job.file_url = file_url
    job.file_name = file_name
    job.row_count = row_count
    job.finished_at = now
    job.error_message = None
    await write_audit_log(
        db,
        tenant_id=job.tenant_id,
        user_id=job.user_id,
        operation_type="export.succeeded",
        target_type="export_job",
        target_id=job.id,
        after={
            "status": job.status,
            "file_url": job.file_url,
            "file_name": job.file_name,
            "row_count": job.row_count,
        },
    )
    await db.flush()
    return job


async def mark_export_failed(
    db: AsyncSession,
    job: ExportJob,
    *,
    error_message: str,
) -> ExportJob:
    """标记失败并写审计 export.failed（短文案，无堆栈）。"""
    now = datetime.now(timezone.utc)
    job.status = "failed"
    job.error_message = _short_error(error_message)
    job.finished_at = now
    await write_audit_log(
        db,
        tenant_id=job.tenant_id,
        user_id=job.user_id,
        operation_type="export.failed",
        target_type="export_job",
        target_id=job.id,
        after={"status": job.status, "error_message": job.error_message},
        result="failure",
        error_message=job.error_message,
    )
    await db.flush()
    return job


def _is_download_expired(job: ExportJob, *, now: datetime | None = None) -> bool:
    """判断产物是否已过期（status=expired 或超过 expires_at）。"""
    if job.status == "expired":
        return True
    if job.expires_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    expires = job.expires_at
    # DB 可能返回 naive datetime，统一按 UTC 比较
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires < current


async def download_export_job(
    db: AsyncSession,
    user: User,
    job_id: UUID,
    *,
    expires: int = _DOWNLOAD_PRESIGN_EXPIRES,
) -> dict[str, Any]:
    """签发导出产物预签名下载 URL；仅 succeeded 且未过期。

    校验 bucket==exports 且 object key 属于本租户前缀；写审计 export.download。
    返回 {"url": ..., "expires_in": expires}。
    """
    job = await get_export_job(db, user, job_id)

    if job.status != "succeeded" or _is_download_expired(job):
        raise BusinessError(
            "导出文件不可下载（未完成或已过期）",
            code="EXPORT_NOT_DOWNLOADABLE",
        )
    if not job.file_url:
        raise BusinessError(
            "导出文件不可下载（未完成或已过期）",
            code="EXPORT_NOT_DOWNLOADABLE",
        )

    try:
        bucket, key = parse_s3_url(job.file_url)
    except ValueError as exc:
        raise BusinessError(
            "导出文件地址无效",
            code="EXPORT_INVALID_FILE",
        ) from exc

    if bucket != settings.minio_bucket_exports:
        raise ForbiddenError("无权访问该导出文件", code="EXPORT_FILE_FORBIDDEN")

    tenant_prefix = f"{user.tenant_id}/"
    if not key.startswith(tenant_prefix):
        raise ForbiddenError("无权访问该导出文件", code="EXPORT_FILE_FORBIDDEN")

    try:
        url = storage_service.get_presigned_url(bucket, key, expires=expires)
    except Exception as exc:
        raise BusinessError(
            f"生成下载链接失败：{exc}",
            code="EXPORT_PRESIGN_FAILED",
        ) from exc

    await write_audit_log(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        operation_type="export.download",
        target_type="export_job",
        target_id=job.id,
        after={
            "file_url": job.file_url,
            "file_name": job.file_name,
            "expires_in": expires,
        },
    )
    return {"url": url, "expires_in": expires}


async def retry_export_job(
    db: AsyncSession,
    user: User,
    job_id: UUID,
) -> tuple[ExportJob, bool]:
    """仅 failed 任务可重试：按原 filters 走 create_export_job（可能幂等命中）。

    返回 (job, deduplicated)；Celery delay 仍由 API 层对新建任务触发。
    """
    job = await get_export_job(db, user, job_id)
    if job.status != "failed":
        raise BusinessError(
            "仅失败的导出任务可重试",
            code="EXPORT_RETRY_NOT_ALLOWED",
        )
    return await create_export_job(
        db,
        user,
        resource_type=job.resource_type,
        filters=dict(job.filters or {}),
    )
