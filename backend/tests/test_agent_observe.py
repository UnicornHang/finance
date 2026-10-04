"""Langfuse 观测：无密钥时不创建客户端。"""

from unittest.mock import MagicMock, patch

from app.agent.observe import is_enabled, record, reset_for_tests


def test_observe_disabled_without_keys():
    """空密钥不启用。"""
    reset_for_tests()
    fake = MagicMock()
    fake.langfuse_public_key = ""
    fake.langfuse_secret_key = ""
    with patch("app.config.get_settings", return_value=fake):
        assert is_enabled() is False
        record("tool", tool="query_policy", tenant_id="t")


def test_observe_records_when_client_present():
    """有客户端时写入 event 名与工具标签。"""
    reset_for_tests()
    fake = MagicMock()
    fake.langfuse_public_key = "pk"
    fake.langfuse_secret_key = "sk"
    fake.langfuse_host = "https://cloud.langfuse.com"
    client = MagicMock()
    with patch("app.config.get_settings", return_value=fake):
        with patch("app.agent.observe._client_tried", True):
            with patch("app.agent.observe._client", client):
                record("tool", tool="query_policy", tenant_id="abc")
    client.event.assert_called()
    kwargs = client.event.call_args.kwargs
    assert kwargs["name"] == "tool"
    assert kwargs["metadata"]["tool"] == "query_policy"
