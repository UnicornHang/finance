"""当前用户账户设置：改资料、改密码。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, or_, select

from app.models import AuditLog, User


async def _cleanup_test_users(db_session, accounts: list[str]) -> None:
    """删除测试用户及其审计日志。"""
    if not accounts:
        return
    result = await db_session.execute(select(User.id).where(User.account.in_(accounts)))
    ids = list(result.scalars().all())
    if ids:
        await db_session.execute(
            delete(AuditLog).where(
                or_(AuditLog.user_id.in_(ids), AuditLog.target_id.in_(ids))
            )
        )
        await db_session.execute(delete(User).where(User.id.in_(ids)))
        await db_session.commit()


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    """未登录不能读当前用户。"""
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_employee_can_read_and_update_profile(
    client: AsyncClient, employee_headers
):
    """员工可读自己的资料并改姓名/部门；角色与账号不变。"""
    r = await client.get("/api/v1/auth/me", headers=employee_headers)
    assert r.status_code == 200, r.text
    original = r.json()
    assert original["account"] == "employee01"
    assert original["role"] == "employee"

    try:
        r2 = await client.patch(
            "/api/v1/auth/me",
            json={"name": "账户设置测试", "dept": "测试部", "role": "admin"},
            headers=employee_headers,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["name"] == "账户设置测试"
        assert body["dept"] == "测试部"
        assert body["role"] == "employee"
        assert body["account"] == "employee01"
    finally:
        await client.patch(
            "/api/v1/auth/me",
            json={"name": original["name"], "dept": original.get("dept")},
            headers=employee_headers,
        )


@pytest.mark.asyncio
async def test_change_password_wrong_old_is_400(
    client: AsyncClient, employee_headers
):
    """旧密码错误返回 400，而不是 401，避免前端误登出。"""
    r = await client.post(
        "/api/v1/auth/me/password",
        json={"old_password": "definitely-wrong", "new_password": "NewPass@1234"},
        headers=employee_headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "WRONG_PASSWORD"


@pytest.mark.asyncio
async def test_change_password_then_login(
    client: AsyncClient, auth_headers, db_session
):
    """改密成功后旧密码失效、新密码可登录。"""
    account = f"utest_acct_{uuid4().hex[:10]}"
    created_id = None
    try:
        r = await client.post(
            "/api/v1/users/",
            json={
                "name": "改密用户",
                "account": account,
                "password": "TempPass@123",
                "role": "employee",
                "dept": "测试部",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        created_id = r.json()["id"]

        login = await client.post(
            "/api/v1/auth/login",
            data={"username": account, "password": "TempPass@123"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        same = await client.post(
            "/api/v1/auth/me/password",
            json={"old_password": "TempPass@123", "new_password": "TempPass@123"},
            headers=headers,
        )
        assert same.status_code == 400
        assert same.json()["code"] == "PASSWORD_UNCHANGED"

        changed = await client.post(
            "/api/v1/auth/me/password",
            json={"old_password": "TempPass@123", "new_password": "NewerPass@456"},
            headers=headers,
        )
        assert changed.status_code == 200, changed.text

        old_login = await client.post(
            "/api/v1/auth/login",
            data={"username": account, "password": "TempPass@123"},
        )
        assert old_login.status_code == 401

        new_login = await client.post(
            "/api/v1/auth/login",
            data={"username": account, "password": "NewerPass@456"},
        )
        assert new_login.status_code == 200, new_login.text
    finally:
        if created_id:
            await _cleanup_test_users(db_session, [account])
