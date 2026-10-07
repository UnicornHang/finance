"""审计日志查询窗口与脱敏快照。不连数据库。"""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.models import LlmConfig
from app.services.audit_service import (
    operation_label,
    resolve_time_window,
    retention_floor,
    summarize_audit,
)
from app.services.llm_config_service import LlmConfigService


def test_unknown_operation_falls_back_to_raw_value():
    """未登记的操作类型原样展示，避免列表出现空白。"""
    assert operation_label("login") == "登录"
    assert operation_label("custom.op") == "custom.op"


def test_time_window_clamps_to_one_year():
    """开始日期早于保留期时，收成保留期起点。"""
    now = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)
    floor = retention_floor(now)
    start, end = resolve_time_window(date(2020, 1, 1), date(2026, 10, 7), now=now)
    assert start == floor
    assert end is not None
    assert end > start
    assert end - timedelta(days=1) <= datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc)


def test_open_ended_window_has_no_end():
    """不传结束日时只限制起点。"""
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    start, end = resolve_time_window(None, None, now=now)
    assert start == retention_floor(now)
    assert end is None


def test_summary_prefers_error_then_title():
    """失败原因优先；否则取标题等短字段。"""
    assert summarize_audit({"title": "制度"}, "密码错误") == "密码错误"
    assert summarize_audit({"filename": "a.pdf"}, None) == "a.pdf"
    assert summarize_audit({}, None) == ""


def test_llm_audit_snapshot_omits_secrets():
    """LLM 审计快照不包含明文或密文密钥。"""
    cfg = LlmConfig(
        id=uuid4(),
        tenant_id=uuid4(),
        scene="chat",
        model="gpt-4o",
        provider="openai",
        api_key_encrypted="fernet-ciphertext",
        enabled=True,
    )
    snap = LlmConfigService.to_audit_dict(cfg)
    assert snap["has_api_key"] is True
    assert "api_key" not in snap
    assert "api_key_encrypted" not in snap
    assert "fernet-ciphertext" not in snap.values()
