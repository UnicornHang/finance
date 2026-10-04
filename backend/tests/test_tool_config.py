"""工具配置：Key 掩码与占位符。"""

from app.services.tool_config_service import is_placeholder_api_key, mask_api_key
from app.services.web_search_service import WebSearchRuntime


def test_placeholder_api_key():
    """空值和星号掩码不算新 Key。"""
    assert is_placeholder_api_key(None)
    assert is_placeholder_api_key("")
    assert is_placeholder_api_key("   ")
    assert is_placeholder_api_key("****")
    assert is_placeholder_api_key("••••")
    assert not is_placeholder_api_key("tvly-real-key")


def test_mask_api_key_keeps_last_four():
    """列表只暴露末四位。"""
    assert mask_api_key(None) is None
    assert mask_api_key("abcd") == "****"
    assert mask_api_key("sk-abcdefgh") == "****efgh"


def test_runtime_from_settings_has_provider():
    """env 兜底至少能构造运行时对象。"""
    rt = WebSearchRuntime.from_settings()
    assert rt.provider in ("bocha", "tavily")
    assert rt.timeout > 0
