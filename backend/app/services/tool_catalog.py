"""工具目录：可配置的外部工具及提供商元数据。"""

from __future__ import annotations

# Agent 工具名；库内旧记录可能仍为 search_official_policy
TOOL_SEARCH_OFFICIAL_DATA = "search_official_data"
TOOL_SEARCH_OFFICIAL_POLICY_LEGACY = "search_official_policy"
# 兼容旧导入名
TOOL_SEARCH_OFFICIAL_POLICY = TOOL_SEARCH_OFFICIAL_DATA

TOOL_CATALOG: dict[str, dict] = {
    TOOL_SEARCH_OFFICIAL_DATA: {
        "label": "权威财税检索",
        "description": "按财政部、税务总局及省级政府门户等白名单检索公开政策与财政数据，并可抓取官方原文",
        "providers": {
            "bocha": {
                "label": "博查",
                "default_base_url": "https://api.bochaai.com/v1/web-search",
                "api_key_help": "在 https://open.bochaai.com/ 创建 API Key",
            },
            "tavily": {
                "label": "Tavily",
                "default_base_url": "https://api.tavily.com/search",
                "api_key_help": "在 https://tavily.com 注册，免费档每月约 1000 credits",
            },
        },
        "legacy_keys": (TOOL_SEARCH_OFFICIAL_POLICY_LEGACY,),
    },
}


def normalize_tool_name(tool_name: str) -> str:
    """把旧工具名规范成目录主 key。"""
    if tool_name == TOOL_SEARCH_OFFICIAL_POLICY_LEGACY:
        return TOOL_SEARCH_OFFICIAL_DATA
    return tool_name


def get_tool_catalog() -> list[dict]:
    """管理端工具列表元数据。"""
    items: list[dict] = []
    for key, meta in TOOL_CATALOG.items():
        providers = [
            {
                "key": pid,
                "label": p["label"],
                "default_base_url": p["default_base_url"],
                "api_key_help": p["api_key_help"],
            }
            for pid, p in (meta.get("providers") or {}).items()
        ]
        items.append(
            {
                "key": key,
                "label": meta["label"],
                "description": meta["description"],
                "providers": providers,
            }
        )
    return items
