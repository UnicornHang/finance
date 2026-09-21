"""pytest 配置。

fixtures:
- client: httpx AsyncClient 绑 FastAPI app（ASGI transport，无网络）
- db_session: SQLAlchemy 异步 session（连接到 .env 配置的真实 DB）
- auth_headers: admin 登录后返回 Authorization 头
- finance_headers: finance01 登录头
- employee_headers: employee01 登录头
"""

import os
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path 中
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# 加载 .env（如果存在）
env_file = BACKEND_ROOT / ".env"
if env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_file)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client():
    """HTTPX 异步 client 直连 ASGI 应用（不占用端口）。"""
    # 延迟导入以保证 sys.path 已就绪
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """异步 DB session。"""
    from app.core.database import async_session_factory

    async with async_session_factory() as session:
        yield session


async def _login(client: AsyncClient, username: str, password: str) -> str:
    """OAuth2 password 表单登录，返回 access_token。"""
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert r.status_code == 200, f"login failed for {username}: {r.text}"
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(client):
    """admin / Admin@123 的 Authorization 头。"""
    token = await _login(client, "admin", "Admin@123")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def finance_headers(client):
    """finance01 / Finance@123 的 Authorization 头。"""
    token = await _login(client, "finance01", "Finance@123")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def employee_headers(client):
    """employee01 / Emp@123 的 Authorization 头。"""
    token = await _login(client, "employee01", "Emp@123")
    return {"Authorization": f"Bearer {token}"}