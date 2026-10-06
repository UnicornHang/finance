"""assemble_context 把原文收成 20 条 prompt 副本。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.memory.assemble import assemble_context
from app.agent.memory.budget import OMISSION


def _msg(role: str, content: str, created_at: str):
    return SimpleNamespace(id=uuid4(), role=role, content=content, created_at=created_at)


@pytest.mark.asyncio
async def test_assemble_uses_prompt_copy_and_keeps_twenty():
    """25 条里只向模型暴露最后 20 条，超长条是副本。"""
    long_text = "头" * 1600 + "中" * 500 + "尾" * 400
    rows = [_msg("user", long_text if i == 24 else f"m{i}", f"t{i:02d}") for i in range(25)]
    # loader 按 desc 返回，组装函数会反转成正序
    desc = list(reversed(rows))
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=desc))))
    )
    with patch(
        "app.agent.memory.assemble.chat_file_service.list_by_message_ids",
        AsyncMock(return_value={}),
    ):
        with patch(
            "app.agent.memory.assemble.chat_file_service.prompt_hint",
            return_value="",
        ):
            ctx = await assemble_context(db, uuid4(), uuid4())
    assert ctx.window_count == 20
    assert ctx.history[0]["content"] == "m5"
    assert ctx.history[-1]["content"].startswith("头" * 1500)
    assert OMISSION in ctx.history[-1]["content"]
    assert len(ctx.window_ids) == 20
