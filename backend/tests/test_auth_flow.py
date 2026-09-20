"""Auth + Chat 流式闭环验证。

最小验证：测试 JWT 签发、Token 解码、密码哈希。
不依赖数据库运行，主要验证安全工具 + 数据流。
"""

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


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