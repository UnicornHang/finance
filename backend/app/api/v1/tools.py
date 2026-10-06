"""工具配置管理 API（管理员）。

- GET  /tools/catalog
- GET  /tools/configs
- PUT  /tools/configs/{tool_name}
- POST /tools/configs/{tool_name}/test
- POST /tools/test
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessError, ForbiddenError
from app.core.security import decrypt_field
from app.deps import get_current_user
from app.models import User
from app.services.tool_catalog import (
    TOOL_CATALOG,
    TOOL_SEARCH_OFFICIAL_DATA,
    get_tool_catalog,
    normalize_tool_name,
)
from app.services.tool_config_service import is_placeholder_api_key, tool_config_service
from app.services.web_search_service import web_search_service

router = APIRouter()


class ToolConfigUpsert(BaseModel):
    """保存工具配置。api_key 留空表示不改原 Key。"""

    provider: str = "bocha"
    api_key: str | None = None
    base_url: str | None = None
    enabled: bool = False
    timeout_seconds: int = Field(default=15, ge=5, le=120)
    max_results: int = Field(default=16, ge=1, le=20)
    fetch_pages: int = Field(default=2, ge=0, le=5)
    fetch_max_chars: int = Field(default=4000, ge=500, le=20000)


class ToolConfigTest(BaseModel):
    """保存前试调。"""

    provider: str = "bocha"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = Field(default=15, ge=5, le=120)
    tool_name: str | None = None


def _require_admin(user: User) -> None:
    """工具配置仅管理员/财务可改。"""
    if user.role not in ("admin", "finance"):
        raise ForbiddenError("需要管理员或财务权限")


def _tool_or_400(tool_name: str) -> str:
    """校验工具名并规范成目录主 key。"""
    canonical = normalize_tool_name(tool_name)
    if canonical not in TOOL_CATALOG:
        raise BusinessError(f"未知工具：{tool_name}", code="UNKNOWN_TOOL")
    return canonical


@router.get("/catalog")
async def list_catalog(_: Annotated[User, Depends(get_current_user)]):
    """工具与提供商元数据。"""
    return get_tool_catalog()


@router.get("/configs")
async def list_configs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """列出当前租户工具配置（无明文 Key）。"""
    _require_admin(user)
    return await tool_config_service.list_merged(db, user.tenant_id)


@router.put("/configs/{tool_name}")
async def upsert_config(
    tool_name: str,
    payload: ToolConfigUpsert,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """新增或更新工具配置。"""
    _require_admin(user)
    canonical = _tool_or_400(tool_name)
    cfg = await tool_config_service.upsert(
        db, user.tenant_id, canonical, payload.model_dump()
    )
    return tool_config_service.to_safe_dict(canonical, cfg)


@router.post("/configs/{tool_name}/test")
async def test_saved_config(
    tool_name: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """用已保存配置测检索连通性。"""
    _require_admin(user)
    canonical = _tool_or_400(tool_name)
    runtime = await tool_config_service.resolve_web_search(db, user.tenant_id)
    if canonical != TOOL_SEARCH_OFFICIAL_DATA:
        raise BusinessError("该工具暂不支持连通性测试", code="TEST_UNSUPPORTED")
    return await web_search_service.test_connectivity(runtime)


@router.post("/test")
async def test_payload(
    payload: ToolConfigTest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """保存前用表单值试调；Key 为空则用已存或 env。"""
    _require_admin(user)
    stored_key = ""
    if payload.tool_name:
        _tool_or_400(payload.tool_name)
        row = await tool_config_service.get_row(db, user.tenant_id, payload.tool_name)
        if row and row.api_key_encrypted:
            try:
                stored_key = decrypt_field(row.api_key_encrypted)
            except Exception:
                stored_key = ""
    data = payload.model_dump()
    if is_placeholder_api_key(data.get("api_key")):
        data["api_key"] = None
    runtime = tool_config_service.runtime_from_payload(data, stored_key=stored_key)
    if not runtime.api_key:
        raise BusinessError("需要提供 API Key，或先保存一把 Key", code="NO_API_KEY")
    return await web_search_service.test_connectivity(runtime)
