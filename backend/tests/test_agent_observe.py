"""Agent 观测：本地日志默认开启，Langfuse 需要密钥。"""

import logging
from unittest.mock import MagicMock, patch

from app.agent.observe import is_enabled, record, reset_for_tests


def _settings(*, enabled: bool, public_key: str = "", secret_key: str = "") -> MagicMock:
    """构造观测相关配置。"""
    fake = MagicMock()
    fake.observe_enabled = enabled
    fake.langfuse_public_key = public_key
    fake.langfuse_secret_key = secret_key
    fake.langfuse_host = "https://cloud.langfuse.com"
    return fake


def test_local_observe_on_without_langfuse_keys(caplog):
    """没有 Langfuse 密钥时，本地决策日志仍然写入。"""
    reset_for_tests()
    fake = _settings(enabled=True)
    with patch("app.config.get_settings", return_value=fake):
        assert is_enabled() is True
        with caplog.at_level(logging.INFO, logger="app.agent.observe"):
            record("tool", tool="query_policy", tenant_id="t")
    assert any(
        "agent.observe" in record.message and "query_policy" in record.message
        for record in caplog.records
    )


def test_observe_off_when_flag_false():
    """显式关闭后不再写日志，也不碰 Langfuse。"""
    reset_for_tests()
    fake = _settings(enabled=False)
    with patch("app.config.get_settings", return_value=fake):
        assert is_enabled() is False
        with patch("app.agent.observe.logger") as log:
            record("tool", tool="query_policy", tenant_id="t")
    log.info.assert_not_called()


def test_observe_records_when_client_present():
    """有客户端时写入 event 名与工具标签。"""
    reset_for_tests()
    fake = _settings(enabled=True, public_key="pk", secret_key="sk")
    client = MagicMock()
    with patch("app.config.get_settings", return_value=fake):
        with patch("app.agent.observe._client_tried", True):
            with patch("app.agent.observe._client", client):
                record("tool", tool="query_policy", tenant_id="abc")
    client.event.assert_called()
    kwargs = client.event.call_args.kwargs
    assert kwargs["name"] == "tool"
    assert kwargs["metadata"]["tool"] == "query_policy"
