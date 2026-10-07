"""在 Celery worker 内安全执行 async 协程。

Windows + solo 池下多次 `asyncio.run` 会复用已绑定旧事件循环的连接池，
第二次任务常出现 `Event loop is closed` / `NoneType.send`。
每次跑完后 `engine.dispose()`，强制下次新建连接。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.core.database import engine

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_celery_async(coro: Coroutine[Any, Any, T]) -> T:
    """在 Celery 同步任务里跑协程，结束后释放异步引擎连接。"""

    async def _wrapped() -> T:
        try:
            return await coro
        finally:
            try:
                await engine.dispose()
            except Exception:
                logger.debug("celery async engine dispose failed", exc_info=True)

    return asyncio.run(_wrapped())
