"""历史查询先排除本轮消息再 limit。"""

from uuid import uuid4

from app.agent.memory.loader import recent_messages_stmt


def test_stmt_excludes_current_message_and_limits():
    """SQL 含 id 不等条件，并带 limit。"""
    stmt = recent_messages_stmt(uuid4(), 20, uuid4())
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "messages.id !=" in sql or "messages.id <>" in sql
    assert "LIMIT" in sql.upper()
