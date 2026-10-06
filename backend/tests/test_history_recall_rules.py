"""历史切段与指代启发。"""

from app.agent.memory.history_index import (
    chunk_text,
    format_related_history,
    looks_like_history_reference,
)


def test_chunk_overlap_step_450():
    """1000 字切成步长 450 的段，末段保留剩余。"""
    parts = chunk_text("a" * 1000)
    assert parts[0] == "a" * 500
    assert parts[1] == "a" * 500
    assert parts[1].startswith("a")
    assert len(parts[-1]) == 100
    assert chunk_text("短" * 20) == ["短" * 20]


def test_reference_heuristic():
    """指代旧对话才为真；规章里的「之前」和短确认为假。"""
    assert looks_like_history_reference("上次那张发票的税额")
    assert not looks_like_history_reference("按之前的制度报销")
    assert not looks_like_history_reference("好的")
    assert looks_like_history_reference("好的，上次那张呢")


def test_format_omits_title_when_empty():
    """没有命中时不产生相关历史标题。"""
    assert format_related_history([]) == ""
    text = format_related_history(
        [{"created_at": "2026-10-06 10:00", "role": "assistant", "content": "税额 10 元"}]
    )
    assert "2026-10-06 10:00" in text
    assert "assistant" in text
    assert "税额 10 元" in text
