"""LLM usage 解析与落库。"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.llm_usage_service import parse_usage, record_llm_usage


def test_parse_usage_complete():
    p, c, t, missing = parse_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    assert (p, c, t, missing) == (10, 5, 15, False)


def test_parse_usage_missing_total_sums():
    p, c, t, missing = parse_usage({"prompt_tokens": 10, "completion_tokens": 5})
    assert (p, c, t, missing) == (10, 5, 15, False)


def test_parse_usage_none_is_missing():
    p, c, t, missing = parse_usage(None)
    assert (p, c, t, missing) == (0, 0, 0, True)


def test_parse_usage_object_attrs():
    raw = SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7)
    assert parse_usage(raw) == (3, 4, 7, False)


@pytest.mark.asyncio
async def test_record_skips_without_tenant_or_db(caplog):
    await record_llm_usage(db=None, tenant_id=None, scene="chitchat", source="complete")
    assert any("skip" in r.message.lower() or "跳过" in r.message for r in caplog.records)


def _mock_db_with_nested() -> tuple[AsyncMock, AsyncMock]:
    """构造带 begin_nested savepoint 的 AsyncSession mock。"""
    nested = AsyncMock()
    nested.__aexit__.return_value = False
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    # begin_nested 是同步方法，返回值才能被 async with 进入
    db.begin_nested = MagicMock(return_value=nested)
    return db, nested


@pytest.mark.asyncio
async def test_record_adds_event_and_updates_session():
    """有 tenant + session 时写入事件并 UPDATE sessions 累加。"""
    db, nested = _mock_db_with_nested()
    tid = uuid4()
    sid = uuid4()
    await record_llm_usage(
        db=db,
        tenant_id=tid,
        session_id=sid,
        user_id=None,
        scene="chitchat",
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        usage_missing=False,
        source="complete",
    )
    assert db.add.called
    assert db.execute.await_count >= 1
    assert db.flush.await_count >= 1
    db.begin_nested.assert_called_once()
    nested.__aenter__.assert_awaited()
    nested.__aexit__.assert_awaited()


@pytest.mark.asyncio
async def test_record_flush_failure_isolates_via_savepoint(caplog):
    """flush 失败经 savepoint 隔离，不向外抛，外层 session 仍可用。"""
    db, nested = _mock_db_with_nested()
    db.flush = AsyncMock(side_effect=RuntimeError("table missing"))
    await record_llm_usage(
        db=db,
        tenant_id=uuid4(),
        session_id=uuid4(),
        scene="chitchat",
        source="complete",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )
    db.begin_nested.assert_called_once()
    nested.__aexit__.assert_awaited()
    assert nested.__aexit__.await_args.args[0] is RuntimeError
    # 外层未 rollback；后续 execute 仍可调用
    db.rollback.assert_not_awaited()
    await db.execute("SELECT 1")
    assert db.execute.await_count >= 1
    assert any("落库失败" in r.message for r in caplog.records)
