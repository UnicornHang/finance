"""意图白名单。"""

from app.agent.policy import (
    TOOL_QUERY_POLICY,
    TOOL_SEARCH_OFFICIAL,
    effective_intent,
    required_tool_for_intent,
    status_event_for_tools,
    tools_for_intent,
)
from app.agent.router import Intent


def test_policy_and_public_tax_share_both_tools():
    """制度与公开财税均开放知识库与官方检索。"""
    both = [TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL]
    assert tools_for_intent(Intent.POLICY_QUERY) == both
    assert tools_for_intent(Intent.PUBLIC_TAX) == both
    assert TOOL_SEARCH_OFFICIAL == "search_official_data"


def test_required_tool_is_search_for_public_tax_and_kb_for_policy():
    """公开财税必检索，制度必查库；闲聊没有必调工具。"""
    assert required_tool_for_intent(Intent.PUBLIC_TAX) == TOOL_SEARCH_OFFICIAL
    assert required_tool_for_intent(Intent.POLICY_QUERY) == TOOL_QUERY_POLICY
    assert required_tool_for_intent(Intent.CHITCHAT) is None


def test_portal_and_chitchat_have_no_tools():
    assert tools_for_intent(Intent.OFFICIAL_PORTAL) == []
    assert tools_for_intent(Intent.CHITCHAT) == []
    assert tools_for_intent(Intent.INVOICE_UPLOAD) == []
    assert tools_for_intent(Intent.CONTRACT_UPLOAD) == []
    assert tools_for_intent(Intent.CONFIRM_PENDING) == []


def test_effective_intent_does_not_open_chitchat_tools():
    """未继承时闲聊仍无工具。"""
    intent = effective_intent(Intent.CHITCHAT, None, "今天天气怎么样")
    assert intent == Intent.CHITCHAT
    assert tools_for_intent(intent) == []


def test_status_event_for_official_search_only():
    """仅官方检索时使用联网搜索 status 文案。"""
    assert status_event_for_tools([TOOL_SEARCH_OFFICIAL]) == {
        "type": "status",
        "message": "正在联网搜索…",
    }


def test_status_event_for_dual_tools():
    """双工具白名单使用合并 status 文案。"""
    assert status_event_for_tools([TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL]) == {
        "type": "status",
        "message": "正在检索企业制度并联网搜索…",
    }
