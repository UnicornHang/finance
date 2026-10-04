"""意图到只读工具白名单。硬门禁写在代码里，不只写在 prompt。"""

from app.agent.heuristics import looks_like_confirm_archive, looks_like_followup
from app.agent.router import Intent

TOOL_QUERY_POLICY = "query_policy"
TOOL_SEARCH_OFFICIAL = "search_official_policy"

# 知识库注入门槛，与 ChatService 制度管道一致
POLICY_RAG_MIN_SCORE = 0.35

# 同一轮最多工具→模型 循环次数（含强制补调）
MAX_TOOL_ROUNDS = 2

_INTENT_TOOLS: dict[Intent, tuple[str, ...]] = {
    Intent.POLICY_QUERY: (TOOL_QUERY_POLICY,),
    Intent.PUBLIC_TAX: (TOOL_SEARCH_OFFICIAL,),
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


def tools_for_intent(intent: Intent) -> list[str]:
    """返回该意图允许调用的工具名；未知意图视为闲聊（无工具）。"""
    names = _INTENT_TOOLS.get(intent)
    if names is None:
        return []
    return list(names)


def status_event_for_tools(allowed: list[str]) -> dict | None:
    """进入工具前的 SSE status；无工具则不发。"""
    if TOOL_SEARCH_OFFICIAL in allowed:
        return {
            "type": "status",
            "message": "正在按财政部、税务总局等权威网站检索…",
        }
    if TOOL_QUERY_POLICY in allowed:
        return {
            "type": "status",
            "message": "正在检索企业制度…",
        }
    return None
