"""召回过滤窗口内消息与低分。"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.memory.history_index import filter_recall_rows


def test_filter_drops_window_and_low_score():
    """窗口内 id 与相似度低于 0.35 的行被丢掉，最多留 3 条。"""
    rows = [
        {"message_id": "in", "score": 0.9, "content": "窗内"},
        {"message_id": "a", "score": 0.2, "content": "低分"},
        {"message_id": "b", "score": 0.8, "content": "乙"},
        {"message_id": "c", "score": 0.7, "content": "丙"},
        {"message_id": "d", "score": 0.6, "content": "丁"},
    ]
    kept = filter_recall_rows(rows, exclude_ids={"in"}, limit=3, min_score=0.35)
    assert [row["message_id"] for row in kept] == ["b", "c", "d"]


@pytest.mark.asyncio
async def test_recall_skips_when_embed_fails():
    """嵌入失败时返回空字符串，不回滚，也不开 savepoint。"""
    db = AsyncMock()
    with patch(
        "app.agent.memory.history_index.rag_service.embed",
        AsyncMock(side_effect=RuntimeError("down")),
    ):
        from app.agent.memory.history_index import recall_history

        text = await recall_history(
            db,
            tenant_id=uuid4(),
            session_id=uuid4(),
            question="上次那张发票",
            exclude_ids=set(),
        )
    assert text == ""
    db.rollback.assert_not_awaited()
    db.begin_nested.assert_not_called()


@pytest.mark.asyncio
async def test_recall_rolls_back_when_sql_fails():
    """查询失败时经 async with 退出 savepoint，外层会话不回滚。"""
    nested = AsyncMock()
    # 返回假值，异常才会冒泡，与 AsyncSessionTransaction.__aexit__ 一致
    nested.__aexit__.return_value = False
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("sql"))
    # begin_nested 是同步方法，返回值才能被 async with 进入
    db.begin_nested = MagicMock(return_value=nested)
    with patch(
        "app.agent.memory.history_index.rag_service.embed",
        AsyncMock(return_value=[0.1, 0.2]),
    ):
        from app.agent.memory.history_index import recall_history

        text = await recall_history(
            db,
            tenant_id=uuid4(),
            session_id=uuid4(),
            question="上次那张发票",
            exclude_ids=set(),
        )
    assert text == ""
    db.rollback.assert_not_awaited()
    db.begin_nested.assert_called_once()
    nested.__aenter__.assert_awaited()
    nested.__aexit__.assert_awaited()
    assert nested.__aexit__.await_args.args[0] is RuntimeError
    nested.rollback.assert_not_awaited()
    nested.commit.assert_not_awaited()
