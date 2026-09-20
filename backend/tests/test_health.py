"""健康检查测试。"""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    """健康检查端点。"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_docs_available(client):
    """OpenAPI 文档可访问。"""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema(client):
    """OpenAPI Schema 生成。"""
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "/auth/login" in data["paths"]