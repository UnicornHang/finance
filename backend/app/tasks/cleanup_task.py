"""对象存储垃圾回收：孤儿文件与重复副本。"""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.cleanup_task.cleanup_duplicate_files")
def cleanup_duplicate_files(orphan_hours: int = 24) -> dict:
    """每周日把同一 hash 的引用收拢到一份对象，再删 24h 以上无人引用的附件。"""
    from app.services.file_gc import run_file_gc

    result = asyncio.run(run_file_gc(orphan_hours=orphan_hours))
    logger.info("file gc done %s", result)
    return result
