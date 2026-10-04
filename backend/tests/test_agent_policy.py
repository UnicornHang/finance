"""意图白名单。"""

from app.agent.policy import (
    TOOL_QUERY_POLICY,
    TOOL_SEARCH_OFFICIAL,
    effective_intent,
    tools_for_intent,
)
from app.agent.router import Intent


def test_policy_query_only_knowledge_tool():
    assert tools_for_intent(Intent.POLICY_QUERY) == [TOOL_QUERY_POLICY]


def test_public_tax_only_search_tool():
    assert tools_for_intent(Intent.PUBLIC_TAX) == [TOOL_SEARCH_OFFICIAL]


def test_portal_and_chitchat_have_no_tools():
    assert tools_for_intent(Intent.OFFICIAL_PORTAL) == []
    assert tools_for_intent(Intent.CHITCHAT) == []
    assert tools_for_intent(Intent.INVOICE_UPLOAD) == []
    assert tools_for_intent(Intent.CONTRACT_UPLOAD) == []


def test_effective_intent_does_not_open_chitchat_tools():
    """未继承时闲聊仍无工具。"""
    intent = effective_intent(Intent.CHITCHAT, None, "今天天气怎么样")
    assert intent == Intent.CHITCHAT
    assert tools_for_intent(intent) == []
