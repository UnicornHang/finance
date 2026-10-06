"""会话窗口：固定 20 条，超长消息只截 prompt 副本。"""

from dataclasses import dataclass

WINDOW_SIZE = 20
MESSAGE_CHAR_CAP = 2000
HEAD_CHARS = 1500
TAIL_CHARS = 300
OMISSION = "……（中间已省略，会话记录里有全文）……"


@dataclass(frozen=True)
class HistoryItem:
    """一条已排除本轮用户消息的历史。content 是原文。"""

    id: str
    role: str
    content: str
    created_at: str


@dataclass(frozen=True)
class WindowFit:
    """window 与 prompt_contents 等长。evicted 是窗口之前的原文。"""

    window: tuple[HistoryItem, ...]
    evicted: tuple[HistoryItem, ...]
    prompt_contents: tuple[str, ...]


def prompt_copy(content: str) -> str:
    """超长消息的 prompt 副本。不修改入参。"""
    text = content or ""
    if len(text) <= MESSAGE_CHAR_CAP:
        return text
    return text[:HEAD_CHARS] + OMISSION + text[-TAIL_CHARS:]


def fit_window(items: list[HistoryItem]) -> WindowFit:
    """留下时间正序的最后 20 条。调用方须已排除本轮用户消息。"""
    evicted = tuple(items[:-WINDOW_SIZE]) if len(items) > WINDOW_SIZE else ()
    window = tuple(items[-WINDOW_SIZE:])
    return WindowFit(
        window=window,
        evicted=evicted,
        prompt_contents=tuple(prompt_copy(item.content) for item in window),
    )
