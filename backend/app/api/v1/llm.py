"""LLM 配置管理 API（管理员）。

端点：
- GET    /llm/providers             获取可选 provider 列表
- GET    /llm/scenes               获取场景列表
- GET    /llm/configs              列出当前租户全部场景配置
- GET    /llm/configs/{scene}      查询单个场景配置
- PUT    /llm/configs/{scene}      新增/更新场景配置（upsert）
- DELETE /llm/configs/{scene}      删除场景配置（fallback 到 env）
- POST   /llm/configs/{scene}/test 连通性测试（用入参配置）
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessError, ForbiddenError
from app.core.security import decrypt_field
from app.deps import get_current_user
from app.models import User
from app.services.llm_config_service import llm_config_service
from app.services.llm_service import llm_service
from app.services.providers import get_provider_list, get_scene_list

logger = logging.getLogger(__name__)
router = APIRouter()


# ================ Schemas ================

class LlmConfigUpsert(BaseModel):
    provider: str = "openai"
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=100, le=32000)
    timeout_seconds: int = Field(default=30, ge=5, le=300)
    enabled: bool = True
    extra_params: dict | None = None
    system_prompt: str | None = None  # Phase A：场景级 prompt 持久化


class LlmConfigTest(BaseModel):
    provider: str
    model: str
    api_key: str
    base_url: str | None = None


# ================ Helpers ================

def _require_admin(user: User) -> None:
    if user.role not in ("admin", "finance"):
        raise ForbiddenError("需要管理员或财务权限")


def _scene_or_400(scene: str) -> str:
    from app.services.providers import SCENES
    if scene not in SCENES:
        raise BusinessError(f"未知场景：{scene}", code="UNKNOWN_SCENE")
    return scene


# ================ Provider / Scene 元数据 ================

@router.get("/providers")
async def list_providers(_: Annotated[User, Depends(get_current_user)]):
    """返回支持的 LLM provider 列表（含默认 base_url 与模型清单）。"""
    return get_provider_list()


@router.get("/scenes")
async def list_scenes(_: Annotated[User, Depends(get_current_user)]):
    """返回业务场景列表。"""
    return get_scene_list()


# ================ 配置 CRUD ================

@router.get("/configs")
async def list_configs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """列出当前租户全部场景配置（不含明文 API Key）。"""
    _require_admin(user)
    rows = await llm_config_service.list_by_tenant(db, user.tenant_id)
    return [llm_config_service.to_safe_dict(c) for c in rows]


@router.get("/configs/{scene}")
async def get_config(
    scene: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """查询单个场景配置。"""
    _require_admin(user)
    _scene_or_400(scene)
    cfg = await llm_config_service.get(db, user.tenant_id, scene)
    if not cfg:
        raise BusinessError(f"场景 {scene} 未配置", code="NOT_CONFIGURED")
    return llm_config_service.to_safe_dict(cfg)


@router.put("/configs/{scene}")
async def upsert_config(
    scene: str,
    payload: LlmConfigUpsert,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """新增或更新场景配置。

    - 若 api_key 缺省或为 None，保持原有加密 key 不变
    - 若传 '****' 占位符也视为不变（前端展示用）
    """
    _require_admin(user)
    _scene_or_400(scene)

    from app.services.providers import PROVIDERS
    if payload.provider not in PROVIDERS:
        raise BusinessError(f"不支持的 provider：{payload.provider}", code="UNKNOWN_PROVIDER")

    data = payload.model_dump()
    cfg = await llm_config_service.upsert(db, user.tenant_id, scene, data)
    logger.info("租户 %s 更新 LLM 配置 scene=%s provider=%s model=%s", user.tenant_id, scene, cfg.provider, cfg.model)
    return llm_config_service.to_safe_dict(cfg)


@router.delete("/configs/{scene}")
async def delete_config(
    scene: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """删除场景配置（fallback 到 env 或 mock）。"""
    _require_admin(user)
    _scene_or_400(scene)
    await llm_config_service.delete(db, user.tenant_id, scene)
    return {"deleted": True, "scene": scene}


# ================ 连通性测试 ================

@router.post("/configs/{scene}/test")
async def test_saved_config(
    scene: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """用已保存的配置测试连通性。"""
    _require_admin(user)
    _scene_or_400(scene)
    cfg = await llm_config_service.get(db, user.tenant_id, scene)
    if not cfg or not cfg.api_key_encrypted:
        raise BusinessError(f"场景 {scene} 未配置 API Key", code="NO_API_KEY")
    return await llm_service.test_connectivity(
        provider=cfg.provider,
        model=cfg.model,
        api_key=decrypt_field(cfg.api_key_encrypted),
        base_url=cfg.base_url,
    )


@router.post("/test")
async def test_payload(payload: LlmConfigTest, _: Annotated[User, Depends(get_current_user)]):
    """用入参配置测试连通性（保存前试调）。"""
    return await llm_service.test_connectivity(
        provider=payload.provider,
        model=payload.model,
        api_key=payload.api_key,
        base_url=payload.base_url,
    )
