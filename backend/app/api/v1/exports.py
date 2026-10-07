"""异步导出中心 REST API。

端点：
- POST   /exports/                 创建导出任务（进行中同 fingerprint 幂等）
- GET    /exports/                 当前用户任务列表（分页）
- GET    /exports/{id}             详情
- GET    /exports/{id}/download    预签名下载（仅 succeeded 且未过期）
- POST   /exports/{id}/retry       失败重试（等价新建 + 入队）
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models import ExportJob, User
from app.services import export_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ExportCreateRequest(BaseModel):
    """创建导出任务请求体。"""

    resource_type: Literal["invoice", "contract"]
    filters: dict[str, Any] = Field(default_factory=dict)


def _iso(dt: datetime | None) -> str | None:
    """datetime → ISO 字符串。"""
    return dt.isoformat() if dt is not None else None


def _serialize_job(
    job: ExportJob,
    *,
    deduplicated: bool | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """ExportJob → 响应字典。"""
    payload: dict[str, Any] = {
        "id": str(job.id),
        "status": job.status,
        "resource_type": job.resource_type,
        "artifact_kind": job.artifact_kind,
        "filters": job.filters or {},
        "fingerprint": job.fingerprint,
        "row_count": job.row_count,
        "file_name": job.file_name,
        "error_message": job.error_message,
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "expires_at": _iso(job.expires_at),
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }
    if deduplicated is not None:
        payload["deduplicated"] = deduplicated
    if message is not None:
        payload["message"] = message
    return payload


async def _enqueue_after_commit(db: AsyncSession, job: ExportJob) -> None:
    """任务行已 commit 后入队；delay 失败则标 failed，避免永久占幂等槽。"""
    # 延迟导入，避免缺 PDF/xlsx 依赖时整站 /exports 路由注册失败（表现为 404）
    from app.tasks.export_task import export_artifact

    try:
        result = export_artifact.delay(str(job.id))
    except Exception:
        logger.exception("export enqueue failed job_id=%s", job.id)
        await export_service.mark_export_failed(
            db, job, error_message="导出任务入队失败，请重试"
        )
        await db.commit()
        await db.refresh(job)
        return
    task_id = getattr(result, "id", None) if result is not None else None
    if task_id:
        job.celery_task_id = str(task_id)
        await db.commit()
        await db.refresh(job)


@router.post("/")
async def create_export(
    body: ExportCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """创建导出任务；进行中同 fingerprint 幂等返回，不二次入队。"""
    job, deduplicated = await export_service.create_export_job(
        db,
        user,
        resource_type=body.resource_type,
        filters=body.filters,
    )
    await db.commit()
    await db.refresh(job)
    if not deduplicated:
        await _enqueue_after_commit(db, job)
    message = "已有相同导出任务" if deduplicated else None
    return _serialize_job(job, deduplicated=deduplicated, message=message)


@router.get("/")
async def list_exports(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    resource_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """分页列出当前用户的导出任务。"""
    items, total = await export_service.list_export_jobs(
        db,
        user,
        resource_type=resource_type,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_serialize_job(j) for j in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{job_id}")
async def get_export(
    job_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """导出任务详情（仅本人）。"""
    job = await export_service.get_export_job(db, user, job_id)
    return _serialize_job(job)


@router.get("/{job_id}/download")
async def download_export(
    job_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """签发预签名下载 URL；仅 succeeded 且未过期。"""
    result = await export_service.download_export_job(db, user, job_id)
    await db.commit()
    return result


@router.post("/{job_id}/retry")
async def retry_export(
    job_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """失败任务重试：按原 filters 新建并入队（可能幂等命中进行中任务）。"""
    job, deduplicated = await export_service.retry_export_job(db, user, job_id)
    await db.commit()
    await db.refresh(job)
    if not deduplicated:
        await _enqueue_after_commit(db, job)
    message = "已有相同导出任务" if deduplicated else None
    return _serialize_job(job, deduplicated=deduplicated, message=message)
