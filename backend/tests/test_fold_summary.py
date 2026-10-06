"""窗口外摘要折叠。"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agent.memory.summary import (
    SUMMARY_CHAR_CAP,
    build_summary_prompt,
    fold_outside_window,
    split_fold_batches,
)


def test_prompt_contains_only_supplied_lines_and_cap():
    """提示词含旧摘要与给定行，并要求 800 字、不抄单据 id。"""
    prompt = build_summary_prompt("旧结论", ["user: 住宿 500"])
    assert "旧结论" in prompt
    assert "user: 住宿 500" in prompt
    assert "800" in prompt
    assert "不复制" in prompt or "不要复制" in prompt
    assert SUMMARY_CHAR_CAP == 800


def test_split_fold_batches_respects_8000():
    """单批字符数不超过 8000。"""
    lines = ["字" * 3000, "字" * 3000, "字" * 3000]
    batches = split_fold_batches(lines, max_chars=8000)
    assert len(batches) == 2
    assert sum(len(line) for line in batches[0]) <= 8000


@pytest.mark.asyncio
async def test_fold_skips_llm_when_window_is_short():
    """窗口不足 20 条时不调用摘要模型。"""
    session = type("S", (), {"summary": "旧", "summary_until_message_id": None})()
    with patch("app.agent.memory.summary.llm_service.invoke", AsyncMock()) as invoke:
        await fold_outside_window(
            AsyncMock(),
            session,
            exclude_message_id=uuid4(),
            window_ids=("a", "b"),
        )
    invoke.assert_not_awaited()
    assert session.summary == "旧"


@pytest.mark.asyncio
async def test_fold_keeps_summary_when_llm_fails():
    """摘要模型抛错时不改摘要和游标。"""
    session = type("S", (), {"summary": "旧", "summary_until_message_id": None, "id": uuid4()})()
    db = AsyncMock()
    db.rollback = AsyncMock()
    with patch("app.agent.memory.summary.llm_service.invoke", AsyncMock(side_effect=RuntimeError("down"))):
        with patch(
            "app.agent.memory.summary._outside_lines",
            AsyncMock(return_value=(["user: 旧对话"], uuid4())),
        ):
            await fold_outside_window(
                db,
                session,
                exclude_message_id=uuid4(),
                window_ids=tuple(f"id-{i}" for i in range(20)),
            )
    assert session.summary == "旧"
    assert session.summary_until_message_id is None
    db.rollback.assert_awaited()
