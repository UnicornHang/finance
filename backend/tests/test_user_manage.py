"""用户管理 API 集成测试。

覆盖列表、创建、更新、重置密码、停用、权限隔离与最后一名管理员保护。
测试账号以 utest_ 前缀创建，结束后硬删除以免污染 seed。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, or_, select

from app.models import AuditLog, User


async def _cleanup_test_users(db_session, accounts: list[str]) -> None:
    """删除测试用户及其审计日志，避免 FK 挡住硬删。"""
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


def _create_payload(account: str, **overrides) -> dict:
    """组装创建用户请求体。"""
    body = {
        "name": "测试用户",
        "account": account,
        "password": "TempPass@123",
        "role": "employee",
        "dept": "测试部",
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_list_users_admin_ok(client: AsyncClient, auth_headers):
    """管理员可列出本租户用户。"""
    r = await client.get("/api/v1/users/", headers=auth_headers)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert any(u["account"] == "admin" for u in items)
    assert all("password_hash" not in u for u in items)


@pytest.mark.asyncio
async def test_list_users_forbidden_for_finance_and_employee(
    client: AsyncClient, finance_headers, employee_headers
):
    """财务与员工无权访问用户管理。"""
    r_fin = await client.get("/api/v1/users/", headers=finance_headers)
    r_emp = await client.get("/api/v1/users/", headers=employee_headers)
    assert r_fin.status_code == 403
    assert r_emp.status_code == 403


@pytest.mark.asyncio
async def test_user_crud_reset_and_disable(client: AsyncClient, auth_headers, db_session):
    """创建 → 改角色 → 重置密码可登录 → 停用后不可登录。"""
    account = f"utest_{uuid4().hex[:10]}"
    created_id = None
    try:
        r = await client.post(
            "/api/v1/users/",
            json=_create_payload(account),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        created_id = body["id"]
        assert body["account"] == account
        assert body["role"] == "employee"
        assert body["status"] == "active"

        r2 = await client.patch(
            f"/api/v1/users/{created_id}",
            json={"role": "finance", "dept": "财务部"},
            headers=auth_headers,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["role"] == "finance"
        assert r2.json()["dept"] == "财务部"

        r3 = await client.post(
            f"/api/v1/users/{created_id}/reset-password",
            headers=auth_headers,
        )
        assert r3.status_code == 200, r3.text
        temp = r3.json()["temporary_password"]
        assert len(temp) >= 10

        login = await client.post(
            "/api/v1/auth/login",
            data={"username": account, "password": temp},
        )
        assert login.status_code == 200, login.text

        r4 = await client.delete(f"/api/v1/users/{created_id}", headers=auth_headers)
        assert r4.status_code == 200, r4.text
        assert r4.json()["status"] == "disabled"

        login2 = await client.post(
            "/api/v1/auth/login",
            data={"username": account, "password": temp},
        )
        assert login2.status_code == 401
    finally:
        await _cleanup_test_users(db_session, [account])


@pytest.mark.asyncio
async def test_duplicate_account_conflict(client: AsyncClient, auth_headers, db_session):
    """重复账号返回 409。"""
    account = f"utest_{uuid4().hex[:10]}"
    try:
        r1 = await client.post(
            "/api/v1/users/",
            json=_create_payload(account),
            headers=auth_headers,
        )
        assert r1.status_code == 200, r1.text
        r2 = await client.post(
            "/api/v1/users/",
            json=_create_payload(account, name="另一个"),
            headers=auth_headers,
        )
        assert r2.status_code == 409
    finally:
        await _cleanup_test_users(db_session, [account])


@pytest.mark.asyncio
async def test_cannot_disable_self(client: AsyncClient, auth_headers, db_session):
    """管理员不能停用自己。"""
    me = await client.get("/api/v1/users/", headers=auth_headers)
    admin = next(u for u in me.json() if u["account"] == "admin")
    r = await client.delete(f"/api/v1/users/{admin['id']}", headers=auth_headers)
    assert r.status_code == 400
    assert r.json()["code"] == "SELF_DISABLE"


@pytest.mark.asyncio
async def test_cannot_demote_last_admin(client: AsyncClient, auth_headers):
    """当租户只剩一名启用管理员时，禁止降级。"""
    me = await client.get("/api/v1/users/", headers=auth_headers)
    users = me.json()
    active_admins = [u for u in users if u["role"] == "admin" and u["status"] == "active"]
    admin = next(u for u in users if u["account"] == "admin")
    if len(active_admins) != 1:
        pytest.skip("当前租户存在多名管理员，无法断言最后一名保护")
    r = await client.patch(
        f"/api/v1/users/{admin['id']}",
        json={"role": "finance"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert r.json()["code"] == "LAST_ADMIN"
