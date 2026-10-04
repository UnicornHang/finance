"""B2-1/B2-2：会话记忆块与追问继承。"""

from uuid import uuid4

from app.agent.context import SessionContext, attach_memory
from app.agent.heuristics import looks_like_followup
from app.agent.policy import effective_intent
from app.agent.router import Intent


def test_memory_block_contains_summary_and_pending():
    """记忆块含摘要与 pending，人设在前。"""
    ctx = SessionContext.empty(uuid4(), uuid4(), uuid4(), summary="上次问过差旅")
    ctx.entities = {
        "pending_task": {"kind": "invoice_pending", "id": "inv-1"},
        "uploaded_invoices": {"ids": ["inv-1"]},
        "queried_policies": {"titles": ["差旅报销制度"]},
    }
    block = ctx.memory_block()
    assert "上次问过差旅" in block
    assert "invoice_pending" in block
    assert "inv-1" in block
    assert "差旅报销制度" in block
    merged = attach_memory("你是 MoFan。", ctx)
    assert merged.startswith("你是 MoFan。")
    assert "[会话摘要]" in merged


def test_followup_inherits_policy_not_invoice():
    """闲聊追问只继承制度/公开财税。"""
    assert looks_like_followup("那一线城市呢？")
    assert not looks_like_followup("你好")
    assert not looks_like_followup("帮我查一下发票真伪")

    assert (
        effective_intent(Intent.CHITCHAT, Intent.POLICY_QUERY, "那一线城市呢？")
        == Intent.POLICY_QUERY
    )
    assert (
        effective_intent(Intent.CHITCHAT, Intent.PUBLIC_TAX, "那税率呢")
        == Intent.PUBLIC_TAX
    )
    assert (
        effective_intent(Intent.CHITCHAT, Intent.INVOICE_UPLOAD, "好的")
        == Intent.CHITCHAT
    )
    assert (
        effective_intent(Intent.PUBLIC_TAX, Intent.POLICY_QUERY, "那一线城市呢？")
        == Intent.PUBLIC_TAX
    )


def test_last_intent_parse():
    """从实体还原上一轮意图。"""
    ctx = SessionContext.empty(uuid4(), uuid4(), uuid4())
    ctx.entities = {"last_intent": {"value": "policy_query"}}
    assert ctx.last_intent() == Intent.POLICY_QUERY
