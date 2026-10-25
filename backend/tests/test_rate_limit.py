"""限流解析与内存计数。"""

import pytest

from app.core.exceptions import RateLimitError
from app.core.rate_limit import check_limits, parse_limit


def test_parse_limit_units():
    assert parse_limit("100/minute") == (100, 60)
    assert parse_limit("10/hour") == (10, 3600)
    assert parse_limit("5/second") == (5, 1)


def test_check_limits_trips_on_user(monkeypatch):
    """用户窗口超限抛 429。"""
    monkeypatch.setattr(
        "app.core.rate_limit.settings.rate_limit_per_user",
        "2/minute",
    )
    monkeypatch.setattr(
        "app.core.rate_limit.settings.rate_limit_per_tenant",
        "10000/hour",
    )
    monkeypatch.setattr(
        "app.core.rate_limit.settings.rate_limit_per_ip",
        "1000/minute",
    )
    # 强制走内存路径
    monkeypatch.setattr("app.core.rate_limit._get_redis", lambda: None)
    uid = "user-rl-test"
    check_limits(user_id=uid, tenant_id=None, ip=None)
    check_limits(user_id=uid, tenant_id=None, ip=None)
    with pytest.raises(RateLimitError):
        check_limits(user_id=uid, tenant_id=None, ip=None)
