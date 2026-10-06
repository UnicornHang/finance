"""20 条窗口与单条 prompt 截断。"""

from app.agent.memory.budget import (
    OMISSION,
    WINDOW_SIZE,
    HistoryItem,
    fit_window,
    prompt_copy,
)


def _item(i: int, content: str = "短") -> HistoryItem:
    return HistoryItem(id=f"m{i}", role="user", content=content, created_at=f"2026-10-06T00:{i:02d}:00")


def test_window_is_last_20_of_25():
    """传入 25 条时窗口是最后 20 条，更旧的 5 条在 evicted。"""
    items = [_item(i, f"正文{i}") for i in range(25)]
    fitted = fit_window(items)
    assert WINDOW_SIZE == 20
    assert [m.id for m in fitted.window] == [f"m{i}" for i in range(5, 25)]
    assert [m.id for m in fitted.evicted] == [f"m{i}" for i in range(5)]
    assert fitted.prompt_contents == tuple(f"正文{i}" for i in range(5, 25))
    assert items[0].content == "正文0"


def test_short_session_keeps_all():
    """不足 20 条时全部留在窗口，evicted 为空。"""
    items = [_item(i) for i in range(8)]
    fitted = fit_window(items)
    assert len(fitted.window) == 8
    assert fitted.evicted == ()


def test_prompt_copy_keeps_head_and_tail():
    """超过 2000 字只生成副本，原文不变。"""
    original = ("头" * 1500) + ("中" * 2000) + ("尾" * 300)
    copied = prompt_copy(original)
    assert copied.startswith("头" * 1500)
    assert OMISSION in copied
    assert copied.endswith("尾" * 300)
    assert original == ("头" * 1500) + ("中" * 2000) + ("尾" * 300)
    fitted = fit_window([_item(1, original)])
    assert fitted.window[0].content == original
    assert fitted.prompt_contents[0] == copied


def test_message_at_cap_is_unchanged():
    """正好 2000 字不截断。"""
    text = "字" * 2000
    assert prompt_copy(text) == text


def test_twenty_short_messages_do_not_pull_older():
    """恰好 20 条短消息全部保留。"""
    items = [_item(i, "字" * 100) for i in range(20)]
    fitted = fit_window(items)
    assert len(fitted.window) == 20
    assert fitted.evicted == ()
