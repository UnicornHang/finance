"""Auth + Chat 流式闭环验证。

最小验证：测试 JWT 签发、Token 解码、密码哈希。
不依赖数据库运行，主要验证安全工具 + 数据流。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AccountLockedError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.services.auth_service import AuthService


def test_password_hash_and_verify():
    """密码哈希 + 验证。"""
    plain = "MyP@ssword123"
    hashed = hash_password(plain)

    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip():
    """Access Token 签发 + 解码。"""
    token = create_access_token(
        subject="user-uuid-123",
        tenant_id="tenant-uuid-456",
        role="admin",
    )
    payload = decode_token(token)

    assert payload["sub"] == "user-uuid-123"
    assert payload["tenant_id"] == "tenant-uuid-456"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_refresh_token_roundtrip():
    """Refresh Token 类型标记。"""
    token = create_refresh_token(subject="user-uuid-123", tenant_id="tenant-uuid-456")
    payload = decode_token(token)

    assert payload["type"] == "refresh"
    assert payload["sub"] == "user-uuid-123"


def test_invalid_token_raises():
    """非法 Token 抛 ValueError。"""
    with pytest.raises(ValueError):
        decode_token("invalid.jwt.string")


def test_access_token_extra_claims():
    """Access Token 支持额外 claims。"""
    token = create_access_token(
        subject="user-123",
        tenant_id="tenant-456",
        role="employee",
        extra_claims={"dept": "财务部"},
    )
    payload = decode_token(token)
    assert payload["dept"] == "财务部"


# ================ 登录锁定 ================

def _lockout_user(**overrides) -> User:
    """构造带锁定字段的测试用户。"""
    user = User(
        id=uuid4(),
        tenant_id=uuid4(),
        name="测试用户",
        account="tester",
        password_hash="hashed",
        role="employee",
        status="active",
        failed_login_attempts=0,
        locked_until=None,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _lockout_db(user: User | None) -> AsyncMock:
    """模拟带 for update 查询的 DB session。"""
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


async def test_unknown_account_generic_error():
    """不存在的账号返回通用错误，不暴露是否存在。"""
    svc = AuthService()
    with pytest.raises(UnauthorizedError, match="账号或密码错误"):
        await svc.authenticate(_lockout_db(None), "nobody", "x")


async def test_wrong_password_increments_and_commits(monkeypatch):
    """密码错误会累加失败次数并提交，避免异常回滚丢失计数。"""
    monkeypatch.setattr("app.services.auth_service.verify_password", lambda *_: False)
    user = _lockout_user(failed_login_attempts=1)
    db = _lockout_db(user)
    svc = AuthService()
    with pytest.raises(UnauthorizedError, match="账号或密码错误"):
        await svc.authenticate(db, "tester", "bad")
    assert user.failed_login_attempts == 2
    assert user.locked_until is None
    db.commit.assert_awaited()


async def test_fifth_failure_locks_account(monkeypatch):
    """第 5 次失败触发锁定，返回 429 语义的锁定异常。"""
    monkeypatch.setattr("app.services.auth_service.verify_password", lambda *_: False)
    user = _lockout_user(failed_login_attempts=4)
    db = _lockout_db(user)
    svc = AuthService()
    with pytest.raises(AccountLockedError, match="账号已锁定"):
        await svc.authenticate(db, "tester", "bad")
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    db.commit.assert_awaited()


async def test_locked_account_rejects_even_correct_password(monkeypatch):
    """锁定期内正确密码也不能登录，且不再累加次数。"""
    monkeypatch.setattr("app.services.auth_service.verify_password", lambda *_: True)
    user = _lockout_user(
        failed_login_attempts=5,
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=20),
    )
    db = _lockout_db(user)
    svc = AuthService()
    with pytest.raises(AccountLockedError, match="账号已锁定"):
        await svc.authenticate(db, "tester", "good")
    assert user.failed_login_attempts == 5


async def test_success_clears_failed_attempts(monkeypatch):
    """登录成功清零失败计数。"""
    monkeypatch.setattr("app.services.auth_service.verify_password", lambda *_: True)
    user = _lockout_user(failed_login_attempts=3)
    db = _lockout_db(user)
    svc = AuthService()
    got = await svc.authenticate(db, "tester", "good")
    assert got is user
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    db.commit.assert_awaited()


async def test_expired_lock_allows_login(monkeypatch):
    """锁定过期后允许用正确密码登录并复位状态。"""
    monkeypatch.setattr("app.services.auth_service.verify_password", lambda *_: True)
    user = _lockout_user(
        failed_login_attempts=5,
        locked_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db = _lockout_db(user)
    svc = AuthService()
    got = await svc.authenticate(db, "tester", "good")
    assert got is user
    assert user.failed_login_attempts == 0
    assert user.locked_until is None