"""LLM 流式输出与助手消息落库（含中断半截）。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SaveMessageFn = Callable[..., Awaitable[Any]]
OnInterrupt = Callable[[], Awaitable[Any]]


@dataclass
class StreamPersistResult:
    """一轮流式结束后的落库结果，供调用方做 auto_title 等副作用。"""

    content: str = ""
    interrupted: bool = False
    saved: bool = False


def merge_tool_calls(base: dict | None, *, interrupted: bool) -> dict | None:
    """合并 base_trace 与 interrupted 标记；成功路径不写入 interrupted 键。"""
    if not interrupted:
        return base
    merged = dict(base or {})
    merged["interrupted"] = True
    return merged


def _clear_pending_cancellation(task: asyncio.Task | None) -> int:
    """摘掉任务上尚未消费的 asyncio 取消计数，返回摘掉的次数。"""
    if task is None:
        return 0
    # CancelledError 被接住后，剩余计数仍会让下一次 await 立刻再抛
    absorbed = task.cancelling()
    while task.uncancel():
        pass
    return absorbed


def _restore_cancellation(task: asyncio.Task | None, absorbed: int) -> None:
    """清理结束后把取消挂回去，让断连继续向外传播。"""
    if task is None:
        return
    for _ in range(absorbed):
        task.cancel()


async def _run_shielded(work: Callable[[], Awaitable[None]]) -> None:
    """在 anyio 屏蔽域里跑完落库或清理。

    Starlette 断连通过取消域对任务投递 CancelledError。屏蔽阻止外层在
    commit 期间再次投递；进入时再清掉已经挂上的取消计数，避免 await 被掐断。
    """
    task = asyncio.current_task()
    absorbed = 0
    try:
        with anyio.CancelScope(shield=True):
            absorbed = _clear_pending_cancellation(task)
            await work()
    finally:
        _restore_cancellation(task, absorbed)


async def stream_llm_and_persist(
    *,
    save_message: SaveMessageFn,
    db: AsyncSession,
    session_id: UUID,
    tenant_id: UUID,
    messages: list,
    scene: str,
    base_tool_calls: dict | None = None,
    result: StreamPersistResult | None = None,
    on_interrupt: OnInterrupt | None = None,
    error_prefix: str = "AI 调用失败",
    yield_error_on_cancel: bool = False,
    **llm_kwargs: Any,
) -> AsyncGenerator[dict, None]:
    """流式调用 LLM；正常或中断时至多落一条助手消息。

    客户端断开时，消费方 aclose 会在 yield 处注入 GeneratorExit，任务取消则
    抛出 CancelledError。两种都先在屏蔽域里落半截并调用 on_interrupt，再原样抛出。
    """
    out = result if result is not None else StreamPersistResult()
    content = ""

    async def _save(interrupted: bool) -> None:
        """写入一条助手消息，并更新本轮结果。调用方负责放进屏蔽域。"""
        await save_message(
            db,
            session_id,
            tenant_id,
            "assistant",
            content,
            tool_calls=merge_tool_calls(base_tool_calls, interrupted=interrupted),
        )
        out.saved = True
        out.interrupted = interrupted
        out.content = content

    async def _save_interrupted() -> None:
        """半截落库，并带上 interrupted。"""
        await _save(True)

    async def _save_final() -> None:
        """正常结束落库，不写 interrupted。"""
        await _save(False)

    async def _interrupt_cleanup() -> None:
        """断连清理：有正文则标中断落库，再执行调用方回调。"""
        if content.strip():
            await _save_interrupted()
        if on_interrupt is None:
            return
        try:
            await on_interrupt()
        except Exception:
            logger.exception("stream on_interrupt failed")

    try:
        async for chunk in llm_service.stream(
            messages,
            scene=scene,
            db=db,
            tenant_id=str(tenant_id),
            **llm_kwargs,
        ):
            content += chunk
            out.content = content
            yield {"type": "text", "content": chunk}
    except (asyncio.CancelledError, GeneratorExit) as exc:
        # aclose 注入的是 GeneratorExit，不能在这里再 yield
        await _run_shielded(_interrupt_cleanup)
        if yield_error_on_cancel and isinstance(exc, asyncio.CancelledError):
            yield {"type": "error", "message": f"{error_prefix}：连接已中断"}
        raise
    except Exception as exc:
        logger.exception("LLM stream failed")
        if content.strip():
            await _run_shielded(_save_interrupted)
        yield {"type": "error", "message": f"{error_prefix}：{exc}"}
        return

    if content.strip():
        # 正常收尾的 commit 同样可能赶在取消域里，屏蔽后再返回
        await _run_shielded(_save_final)
