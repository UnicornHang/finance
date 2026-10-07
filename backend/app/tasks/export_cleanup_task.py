"""异步导出产物过期清理：删 MinIO 对象并将任务标为 expired。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.core.celery_async import run_celery_async
from app.core.database import async_session_factory
from app.models import ExportJob
from app.services.storage_service import parse_s3_url, storage_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _cleanup_expired_exports() -> dict[str, Any]:
    """扫描已过期 succeeded 任务：删 exports 桶对象并置 status=expired。"""
    now = datetime.now(timezone.utc)
    scanned = 0
    expired = 0
    deleted_objects = 0
    skipped = 0
    errors = 0

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(ExportJob).where(
                    ExportJob.status == "succeeded",
                    ExportJob.expires_at.is_not(None),
                    ExportJob.expires_at < now,
                    ExportJob.file_url.is_not(None),
                )
            )
        ).scalars().all()

        for job in rows:
            scanned += 1
            file_url = (job.file_url or "").strip()
            if not file_url:
                skipped += 1
                continue
            try:
                bucket, key = parse_s3_url(file_url)
            except ValueError:
                logger.warning(
                    "export cleanup: invalid file_url job=%s url=%s",
                    job.id,
                    file_url,
                )
                errors += 1
                continue

            if bucket != settings.minio_bucket_exports:
                logger.warning(
                    "export cleanup: skip non-exports bucket job=%s bucket=%s",
                    job.id,
                    bucket,
                )
                skipped += 1
                continue

            try:
                storage_service.delete_file(bucket, key)
                deleted_objects += 1
            except Exception:
                logger.exception(
                    "export cleanup: delete failed job=%s url=%s",
                    job.id,
                    file_url,
                )
                errors += 1
                continue

            job.status = "expired"
            expired += 1

        if expired:
            await db.commit()
        else:
            await db.rollback()

    result = {
        "scanned": scanned,
        "expired": expired,
        "deleted_objects": deleted_objects,
        "skipped": skipped,
        "errors": errors,
    }
    logger.info("export cleanup done %s", result)
    return result


@celery_app.task(name="app.tasks.export_cleanup_task.cleanup_expired_exports")
def cleanup_expired_exports() -> dict[str, Any]:
    """Celery Beat 入口：每日清理过期导出文件。"""
    return run_celery_async(_cleanup_expired_exports())
