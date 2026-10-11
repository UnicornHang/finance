"""意图到只读工具白名单。硬门禁写在代码里，不只写在 prompt。"""

from app.agent.heuristics import looks_like_confirm_archive, looks_like_followup
from app.agent.router import Intent

TOOL_QUERY_POLICY = "query_policy"
TOOL_SEARCH_OFFICIAL = "search_official_data"

# 知识库注入门槛，与 ChatService 制度管道一致
POLICY_RAG_MIN_SCORE = 0.35

# 同一轮最多执行工具的次数。必调工具由代码补上，不靠模型自觉。
MAX_TOOL_ROUNDS = 2

# 制度与公开财税均可查知识库与官方数据，由模型选用
_BOTH_RETRIEVAL_TOOLS: tuple[str, ...] = (TOOL_QUERY_POLICY, TOOL_SEARCH_OFFICIAL)

_INTENT_TOOLS: dict[Intent, tuple[str, ...]] = {
    Intent.POLICY_QUERY: _BOTH_RETRIEVAL_TOOLS,
    Intent.PUBLIC_TAX: _BOTH_RETRIEVAL_TOOLS,
    Intent.OFFICIAL_PORTAL: (),
    Intent.CHITCHAT: (),
    Intent.INVOICE_UPLOAD: (),
    Intent.CONTRACT_UPLOAD: (),
    Intent.CONFIRM_PENDING: (),
}


_INHERITABLE_INTENTS = frozenset({Intent.POLICY_QUERY, Intent.PUBLIC_TAX})


def effective_intent(
    classified: Intent, last: Intent | None, text: str
) -> Intent:
    """本轮分类优先；仅闲聊且像追问时继承上一轮制度或公开财税。"""
    if classified != Intent.CHITCHAT:
        return classified
    if looks_like_confirm_archive(text):
        return Intent.CONFIRM_PENDING
    if last not in _INHERITABLE_INTENTS:
        return classified
    if looks_like_followup(text):
        return last
    return classified


# 这些意图没有检索结果就不能作答；模型漏调时由代码用本轮原话补调。
_REQUIRED_TOOL: dict[Intent, str] = {
    Intent.PUBLIC_TAX: TOOL_SEARCH_OFFICIAL,
    Intent.POLICY_QUERY: TOOL_QUERY_POLICY,
}


def tools_for_intent(intent: Intent) -> list[str]:
    """返回该意图允许调用的工具名；未知意图视为闲聊（无工具）。"""
    names = _INTENT_TOOLS.get(intent)
    if names is None:
        return []
    return list(names)


def required_tool_for_intent(intent: Intent) -> str | None:
    """回答前必须执行的工具。公开财税必联网检索，企业制度必查知识库。"""
    return _REQUIRED_TOOL.get(intent)


def status_event_for_tools(allowed: list[str]) -> dict | None:
    """进入工具前的 SSE status；无工具则不发。"""
    has_policy = TOOL_QUERY_POLICY in allowed
    has_official = TOOL_SEARCH_OFFICIAL in allowed
    if has_policy and has_official:
        return {"type": "status", "message": "正在检索企业制度并联网搜索…"}
    if has_official:
        return {"type": "status", "message": "正在联网搜索…"}
    if has_policy:
        return {
            "type": "status",
            "message": "正在检索企业制度…",
        }
    return None
