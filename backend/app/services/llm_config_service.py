"""LLM 配置管理服务。

读写 `llm_configs` 表；API Key 使用 Fernet 加密存储。
提供按 (tenant_id, scene) 的解析能力，供 LLMService 优先使用。
"""

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError
from app.core.security import decrypt_field, encrypt_field
from app.services.audit_service import write_audit_log

if TYPE_CHECKING:
    from app.models import LlmConfig

logger = logging.getLogger(__name__)


# 内存缓存：避免每次对话都查 DB
# 结构：{(tenant_id, scene): {"api_key": "...", "model": "...", "base_url": "...", ...}}
_config_cache: dict[tuple[str, str], dict] = {}
_CACHE_TTL_SECONDS = 60
_cache_timestamps: dict[tuple[str, str], float] = {}

import time


class LlmConfigService:
    """LLM 配置 CRUD + 解析。"""

    # ================ CRUD ================

    async def list_by_tenant(self, db: AsyncSession, tenant_id: UUID) -> list["LlmConfig"]:
        """列出某租户的所有场景配置。"""
        from app.models import LlmConfig

        result = await db.execute(
            select(LlmConfig).where(LlmConfig.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        scene: str,
        data: dict,
        *,
        actor_id: UUID | None = None,
        ip: str | None = None,
        ua: str | None = None,
    ) -> "LlmConfig":
        """新增或更新某场景配置。

        data 字段：
        - provider: str           provider key（如 openai / deepseek）
        - model: str              模型名
        - api_key: str            明文 API Key（内部加密存储）
        - base_url: str | None    自定义 base_url（custom 时必填）
        - temperature: float
        - max_tokens: int
        - timeout_seconds: int
        - enabled: bool
        - extra_params: dict | None
        """
        from app.models import LlmConfig

        existing = await self._get_one(db, tenant_id, scene)
        before = self.to_audit_dict(existing) if existing else None
        if existing:
            for k, v in data.items():
                if k == "api_key":
                    # 空值和前端占位 **** 都表示密钥未改
                    if v and v != "****":
                        existing.api_key_encrypted = encrypt_field(v)
                    continue
                if hasattr(existing, k):
                    setattr(existing, k, v)
            cfg = existing
        else:
            cfg = LlmConfig(
                tenant_id=tenant_id,
                scene=scene,
                provider=data.get("provider", "openai"),
                model=data["model"],
                api_key_encrypted=encrypt_field(data["api_key"]) if data.get("api_key") else None,
                base_url=data.get("base_url"),
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 2000),
                timeout_seconds=data.get("timeout_seconds", 30),
                enabled=data.get("enabled", True),
                extra_params=data.get("extra_params"),
                system_prompt=data.get("system_prompt"),
            )
            db.add(cfg)

        await db.flush()
        if actor_id is not None:
            after = self.to_audit_dict(cfg)
            raw_key = data.get("api_key")
            # 前端用 **** 占位表示密钥未改，不能当成一次密钥轮换
            after["api_key_updated"] = bool(raw_key) and raw_key != "****"
            await write_audit_log(
                db,
                tenant_id=tenant_id,
                user_id=actor_id,
                operation_type="llm.upsert",
                target_type="llm_config",
                target_id=cfg.id,
                before=before,
                after=after,
                ip=ip,
                ua=ua,
            )
        await db.commit()
        await db.refresh(cfg)
        # 失效缓存
        self._invalidate_cache(tenant_id, scene)
        return cfg

    async def delete(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        scene: str,
        *,
        actor_id: UUID | None = None,
        ip: str | None = None,
        ua: str | None = None,
    ) -> None:
        """删除某场景配置（fallback 到 env）。"""
        cfg = await self._get_one(db, tenant_id, scene)
        if not cfg:
            raise NotFoundError(f"场景 {scene} 不存在配置")
        before = self.to_audit_dict(cfg)
        target_id = cfg.id
        await db.delete(cfg)
        if actor_id is not None:
            await write_audit_log(
                db,
                tenant_id=tenant_id,
                user_id=actor_id,
                operation_type="llm.delete",
                target_type="llm_config",
                target_id=target_id,
                before=before,
                ip=ip,
                ua=ua,
            )
        await db.commit()
        self._invalidate_cache(tenant_id, scene)

    async def get(
        self, db: AsyncSession, tenant_id: UUID, scene: str
    ) -> "LlmConfig | None":
        return await self._get_one(db, tenant_id, scene)

    async def _get_one(
        self, db: AsyncSession, tenant_id: UUID, scene: str
    ) -> "LlmConfig | None":
        from app.models import LlmConfig

        result = await db.execute(
            select(LlmConfig).where(
                LlmConfig.tenant_id == tenant_id,
                LlmConfig.scene == scene,
            )
        )
        return result.scalars().first()

    # ================ 解析（DB 优先，env 兜底） ================

    async def resolve(
        self, db: AsyncSession, tenant_id: UUID, scene: str
    ) -> dict | None:
        """解析场景配置。

        返回 {"api_key", "model", "base_url", "provider", "timeout"}，
        若 DB 没有配置或 disabled 则返回 None（让上层走 env 兜底）。
        """
        from app.services.providers import PROVIDERS, SCENES

        cache_key = (str(tenant_id), scene)
        now = time.time()
        cached = _config_cache.get(cache_key)
        if cached and (now - _cache_timestamps.get(cache_key, 0)) < _CACHE_TTL_SECONDS:
            return cached

        cfg = await self._get_one(db, tenant_id, scene)
        if not cfg or not cfg.enabled:
            # 缓存 None 避免重复查询
            _config_cache[cache_key] = None
            _cache_timestamps[cache_key] = now
            return None

        api_key = (
            decrypt_field(cfg.api_key_encrypted) if cfg.api_key_encrypted else ""
        )

        # base_url 缺省或不是 http(s) 地址时，用该服务商的默认接口
        provider_cfg = PROVIDERS.get(cfg.provider, {})
        raw_base = (cfg.base_url or "").strip()
        if raw_base.startswith("http://") or raw_base.startswith("https://"):
            base_url = raw_base
        else:
            base_url = provider_cfg.get("base_url", "")

        result = {
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": float(cfg.temperature) if cfg.temperature else 0.7,
            "max_tokens": cfg.max_tokens or 2000,
            "timeout": cfg.timeout_seconds or 30,
            "system_prompt": cfg.system_prompt,
        }

        _config_cache[cache_key] = result
        _cache_timestamps[cache_key] = now
        return result

    @staticmethod
    def _invalidate_cache(tenant_id: UUID, scene: str) -> None:
        _config_cache.pop((str(tenant_id), scene), None)
        _cache_timestamps.pop((str(tenant_id), scene), None)

    @staticmethod
    def invalidate_all() -> None:
        """失效全部缓存（管理后台启用/禁用时调用）。"""
        _config_cache.clear()
        _cache_timestamps.clear()

    # ================ 安全序列化（不返回明文 API Key） ================

    @staticmethod
    def to_audit_dict(cfg: "LlmConfig") -> dict:
        """审计快照。只记是否配置了 Key，不记明文或密文。"""
        return {
            "scene": cfg.scene,
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "temperature": float(cfg.temperature) if cfg.temperature else 0.7,
            "max_tokens": cfg.max_tokens,
            "timeout_seconds": cfg.timeout_seconds,
            "enabled": cfg.enabled,
            "has_api_key": bool(cfg.api_key_encrypted),
        }

    @staticmethod
    def to_safe_dict(cfg: "LlmConfig") -> dict:
        """转换为可安全返回前端的字典（api_key 标记为已设置，不泄露明文）。"""
        return {
            "id": str(cfg.id),
            "tenant_id": str(cfg.tenant_id),
            "scene": cfg.scene,
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "temperature": float(cfg.temperature) if cfg.temperature else 0.7,
            "max_tokens": cfg.max_tokens,
            "timeout_seconds": cfg.timeout_seconds,
            "enabled": cfg.enabled,
            "has_api_key": bool(cfg.api_key_encrypted),
            "api_key_masked": (
                "****" + cfg.api_key_encrypted[-8:] if cfg.api_key_encrypted and len(cfg.api_key_encrypted) >= 8 else "****"
            ) if cfg.api_key_encrypted else None,
            "system_prompt": cfg.system_prompt,
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
        }


llm_config_service = LlmConfigService()
