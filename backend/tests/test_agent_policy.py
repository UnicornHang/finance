"""意图白名单。"""

from app.agent.policy import (
    TOOL_QUERY_POLICY,
    TOOL_SEARCH_OFFICIAL,
    effective_intent,
    needs_retrieval,
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


def test_retrieval_intents_do_not_lock_a_single_tool():
    """公开财税和制度都要检索，但不指定唯一工具。"""
    assert needs_retrieval(Intent.PUBLIC_TAX)
    assert needs_retrieval(Intent.POLICY_QUERY)
    assert not needs_retrieval(Intent.CHITCHAT)
    both = [TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL]
    assert tools_for_intent(Intent.PUBLIC_TAX) == both
    assert tools_for_intent(Intent.POLICY_QUERY) == both


def test_portal_has_no_tools_and_chitchat_may_search():
    assert tools_for_intent(Intent.OFFICIAL_PORTAL) == []
    assert tools_for_intent(Intent.CHITCHAT) == [
        TOOL_QUERY_POLICY,
        TOOL_SEARCH_OFFICIAL,
    ]
    assert not needs_retrieval(Intent.CHITCHAT)
    assert tools_for_intent(Intent.INVOICE_UPLOAD) == []
    assert tools_for_intent(Intent.CONTRACT_UPLOAD) == []
    assert tools_for_intent(Intent.CONFIRM_PENDING) == []


def test_effective_intent_keeps_plain_chitchat():
    """未继承时仍是闲聊，但允许自行决定是否检索。"""
    intent = effective_intent(Intent.CHITCHAT, None, "今天天气怎么样")
    assert intent == Intent.CHITCHAT
    assert TOOL_SEARCH_OFFICIAL in tools_for_intent(intent)


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
