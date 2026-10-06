"""流式半截落库封装。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import anyio
import pytest

from app.services.stream_persist import (
    StreamPersistResult,
    merge_tool_calls,
    stream_llm_and_persist,
)


def test_merge_tool_calls_interrupted_keeps_sources():
    base = {"tool": "search_official_data", "sources": [{"index": 1, "url": "https://a"}]}
    out = merge_tool_calls(base, interrupted=True)
    assert out["interrupted"] is True
    assert out["sources"][0]["url"] == "https://a"
    assert merge_tool_calls(None, interrupted=False) is None
    assert merge_tool_calls(base, interrupted=False) is base


@pytest.mark.asyncio
async def test_success_saves_without_interrupted():
    result = StreamPersistResult()
    save = AsyncMock()

    async def fake_stream(*args, **kwargs):
        yield "你好"
        yield "世界"

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        events = []
        async for ev in stream_llm_and_persist(
            save_message=save,
            db=MagicMock(),
            session_id=uuid4(),
            tenant_id=uuid4(),
            messages=[],
            scene="chitchat",
            result=result,
        ):
            events.append(ev)

    assert [e["content"] for e in events if e["type"] == "text"] == ["你好", "世界"]
    assert result.content == "你好世界"
    assert result.interrupted is False
    assert result.saved is True
    save.assert_awaited_once()
    tool_calls = save.await_args.kwargs.get("tool_calls")
    assert not (isinstance(tool_calls, dict) and tool_calls.get("interrupted"))


@pytest.mark.asyncio
async def test_midstream_error_saves_partial_interrupted():
    result = StreamPersistResult()
    save = AsyncMock()

    async def fake_stream(*args, **kwargs):
        yield "半截"
        raise RuntimeError("rate limit")

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        events = []
        async for ev in stream_llm_and_persist(
            save_message=save,
            db=MagicMock(),
            session_id=uuid4(),
            tenant_id=uuid4(),
            messages=[],
            scene="chitchat",
            base_tool_calls={"tool": "search_official_data", "hit_count": 1},
            result=result,
            error_prefix="AI 调用失败",
        ):
            events.append(ev)

    assert any(e["type"] == "error" and "rate limit" in e["message"] for e in events)
    assert result.interrupted is True
    assert result.saved is True
    assert result.content == "半截"
    tool_calls = save.await_args.kwargs["tool_calls"]
    assert tool_calls["interrupted"] is True
    assert tool_calls["tool"] == "search_official_data"


@pytest.mark.asyncio
async def test_error_with_no_chunks_does_not_save():
    result = StreamPersistResult()
    save = AsyncMock()

    async def fake_stream(*args, **kwargs):
        raise RuntimeError("boom")
        yield  # noqa: make async gen

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        events = []
        async for ev in stream_llm_and_persist(
            save_message=save,
            db=MagicMock(),
            session_id=uuid4(),
            tenant_id=uuid4(),
            messages=[],
            scene="chitchat",
            result=result,
        ):
            events.append(ev)

    save.assert_not_awaited()
    assert result.saved is False
    assert result.interrupted is False
    assert any(e["type"] == "error" for e in events)


def _persist_kwargs(result: StreamPersistResult, save, on_interrupt=None) -> dict:
    """组装 stream_llm_and_persist 的公共关键字参数。"""
    kwargs = {
        "save_message": save,
        "db": MagicMock(),
        "session_id": uuid4(),
        "tenant_id": uuid4(),
        "messages": [],
        "scene": "chitchat",
        "result": result,
    }
    if on_interrupt is not None:
        kwargs["on_interrupt"] = on_interrupt
    return kwargs


@pytest.mark.asyncio
async def test_cancelled_saves_partial_and_reraises():
    """消费任务在半截之后被 cancel：落库 interrupted，回调执行，再抛出 CancelledError。"""
    result = StreamPersistResult()
    order: list[str] = []
    seen = asyncio.Event()

    captured: dict = {}

    async def save(*args, **kwargs):
        await asyncio.sleep(0)
        order.append("save")
        captured.update(kwargs)

    async def on_interrupt():
        order.append("hook")

    async def fake_stream(*args, **kwargs):
        yield "已生成"
        await asyncio.Event().wait()

    async def consume():
        async for ev in stream_llm_and_persist(**_persist_kwargs(result, save, on_interrupt)):
            if ev.get("type") == "text":
                seen.set()

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        task = asyncio.create_task(consume())
        await seen.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert order == ["save", "hook"]
    assert result.interrupted is True
    assert result.saved is True
    assert result.content == "已生成"
    assert captured["tool_calls"]["interrupted"] is True


@pytest.mark.asyncio
async def test_aclose_after_partial_yield_saves_interrupted():
    """消费方 aclose 在 yield 处注入 GeneratorExit，半截仍要落库。"""
    result = StreamPersistResult()
    order: list[str] = []
    captured: dict = {}

    async def save(*args, **kwargs):
        order.append("save")
        captured.update(kwargs)

    async def on_interrupt():
        order.append("hook")

    async def fake_stream(*args, **kwargs):
        yield "已生成"
        yield "更多"

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        agen = stream_llm_and_persist(**_persist_kwargs(result, save, on_interrupt))
        first = await agen.__anext__()
        assert first["content"] == "已生成"
        await agen.aclose()

    assert order == ["save", "hook"]
    assert result.interrupted is True
    assert result.saved is True
    assert result.content == "已生成"
    assert captured["tool_calls"]["interrupted"] is True


@pytest.mark.asyncio
async def test_aclose_without_text_skips_save_but_runs_hook():
    """还没吐出正文就关闭时不写空消息，附件清理回调仍要跑。"""
    result = StreamPersistResult()
    saved = False
    hooked = False

    async def save(*args, **kwargs):
        nonlocal saved
        saved = True

    async def on_interrupt():
        nonlocal hooked
        hooked = True

    async def fake_stream(*args, **kwargs):
        yield "   "
        yield "不会读到"

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        agen = stream_llm_and_persist(**_persist_kwargs(result, save, on_interrupt))
        await agen.__anext__()
        await agen.aclose()

    assert saved is False
    assert hooked is True
    assert result.saved is False
    assert result.interrupted is False


@pytest.mark.asyncio
async def test_exception_does_not_call_on_interrupt():
    """业务异常仍由调用方收尾，不走断连回调，避免附件状态写两次。"""
    result = StreamPersistResult()
    save = AsyncMock()
    hook = AsyncMock()

    async def fake_stream(*args, **kwargs):
        yield "半截"
        raise RuntimeError("rate limit")

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream
        async for _ in stream_llm_and_persist(**_persist_kwargs(result, save, hook)):
            pass

    save.assert_awaited_once()
    hook.assert_not_awaited()
    assert result.interrupted is True


@pytest.mark.asyncio
async def test_success_save_survives_anyio_cancel_during_commit():
    """成功路径的 commit 处于屏蔽域时，外层取消域不能把它掐断。"""
    result = StreamPersistResult()
    started = asyncio.Event()
    release = asyncio.Event()
    finished = False
    captured: dict = {}

    async def save(*args, **kwargs):
        nonlocal finished
        started.set()
        await release.wait()
        finished = True
        captured.update(kwargs)

    async def fake_stream(*args, **kwargs):
        yield "完整"

    async def consume():
        async for _ in stream_llm_and_persist(**_persist_kwargs(result, save)):
            pass

    with patch("app.services.stream_persist.llm_service") as mock_llm:
        mock_llm.stream = fake_stream

        async with anyio.create_task_group() as tg:
            tg.start_soon(consume)
            await started.wait()
            tg.cancel_scope.cancel()
            release.set()

    assert finished is True
    assert result.saved is True
    assert result.interrupted is False
    tool_calls = captured.get("tool_calls")
    assert not (isinstance(tool_calls, dict) and tool_calls.get("interrupted"))
