"""对话确认归档：与 REST 共用 service，无 pending 不写库。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agent.context import SessionContext
from app.agent.heuristics import looks_like_confirm_archive
from app.agent.policy import effective_intent, tools_for_intent
from app.agent.router import Intent, heuristic_intent
from app.agent.tools.catalog import build_text_tools
from app.services.chat_service import ChatService


def test_confirm_pending_has_no_tools():
    """确认归档不得暴露 archive Tool。"""
    assert tools_for_intent(Intent.CONFIRM_PENDING) == []
    tools = build_text_tools(MagicMock(), "tenant", {})
    names = {t.name for t in tools}
    assert "archive_invoice" not in names
    assert "archive_contract" not in names


def test_heuristic_and_effective_confirm():
    """确认归档不继承制度白名单。"""
    assert looks_like_confirm_archive("帮我确认归档")
    assert heuristic_intent("确认归档") == Intent.CONFIRM_PENDING
    assert (
        effective_intent(Intent.CHITCHAT, Intent.POLICY_QUERY, "确认归档")
        == Intent.CONFIRM_PENDING
    )


@pytest.mark.asyncio
async def test_confirm_without_pending_does_not_write():
    """无 pending 只提示侧栏，不调用 confirm。"""
    ctx = SessionContext.empty(uuid4(), uuid4(), uuid4())
    service = ChatService()
    service.save_message = AsyncMock()
    events = []
    with patch(
        "app.services.chat_service.invoice_service.confirm", AsyncMock()
    ) as mock_inv:
        with patch(
            "app.services.chat_service.contract_service.confirm", AsyncMock()
        ) as mock_ct:
            async for event in service._stream_confirm_pending(
                AsyncMock(),
                SimpleNamespace(id=uuid4(), tenant_id=uuid4()),
                uuid4(),
                display_msg="确认归档",
                ctx=ctx,
            ):
                events.append(event)
    mock_inv.assert_not_called()
    mock_ct.assert_not_called()
    assert any("侧栏" in (e.get("content") or "") for e in events if e.get("type") == "text")
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_confirm_with_invoice_pending_calls_same_service():
    """有发票 pending 时走 invoice_service.confirm。"""
    invoice_id = uuid4()
    ctx = SessionContext.empty(uuid4(), uuid4(), uuid4())
    ctx.entities = {
        "pending_task": {"kind": "invoice_pending", "id": str(invoice_id)},
    }
    row = SimpleNamespace(
        id=invoice_id,
        invoice_title="t",
        company=None,
        tax_id=None,
        invoice_code=None,
        invoice_number=None,
        invoice_date=None,
        amount_excl_tax=None,
        tax_amount=None,
        amount_incl_tax=None,
        invoice_type=None,
        seller=None,
        buyer=None,
        remark=None,
        file_url=None,
        file_hash=None,
        ocr_confidence=None,
        status="active",
    )
    service = ChatService()
    service.save_message = AsyncMock()
    with patch(
        "app.services.chat_service.invoice_service.confirm",
        AsyncMock(return_value=row),
    ) as mock_inv:
        events = []
        async for event in service._stream_confirm_pending(
            AsyncMock(),
            SimpleNamespace(id=uuid4(), tenant_id=uuid4()),
            uuid4(),
            display_msg="确认归档",
            ctx=ctx,
        ):
            events.append(event)
    mock_inv.assert_awaited_once()
    assert mock_inv.await_args.kwargs["invoice_id"] == invoice_id
    assert any(e.get("type") == "sidepanel" for e in events)
    assert events[-1]["type"] == "done"
