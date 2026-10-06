"""租户工具配置：加密存储 API Key，DB 覆盖 env。"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.core.security import decrypt_field, encrypt_field
from app.models import ToolConfig
from app.services.tool_catalog import (
    TOOL_CATALOG,
    TOOL_SEARCH_OFFICIAL_DATA,
    TOOL_SEARCH_OFFICIAL_POLICY_LEGACY,
    normalize_tool_name,
)
from app.services.web_search_service import SearchProvider, WebSearchRuntime

logger = logging.getLogger(__name__)

_config_cache: dict[tuple[str, str], WebSearchRuntime] = {}
_cache_timestamps: dict[tuple[str, str], float] = {}
_CACHE_TTL_SECONDS = 60


def is_placeholder_api_key(value: str | None) -> bool:
    """空串或掩码占位符视为未改 Key。"""
    if value is None:
        return True
    trimmed = value.strip()
    if not trimmed:
        return True
    return set(trimmed) <= {"*", "•"}


def mask_api_key(plaintext: str | None) -> str | None:
    """列表接口只回末 4 位，禁止回传完整 Key。"""
    if not plaintext:
        return None
    if len(plaintext) <= 4:
        return "****"
    return "****" + plaintext[-4:]


def _is_missing_tool_table(exc: BaseException) -> bool:
    """是否尚未执行 008 迁移。"""
    msg = str(exc).lower()
    return "tool_configs" in msg and "does not exist" in msg


class ToolConfigService:
    """工具配置 CRUD + 解析。"""

    async def list_merged(self, db: AsyncSession, tenant_id: UUID) -> list[dict]:
        """目录中的每个工具一条：有库记录用库，否则用 env 合成。"""
        try:
            rows = await self._list_rows(db, tenant_id)
        except ProgrammingError as exc:
            if not _is_missing_tool_table(exc):
                raise
            logger.warning("tool_configs 表不存在，列表回落到环境变量")
            await db.rollback()
            return [self.to_safe_dict(name, None) for name in TOOL_CATALOG]
        by_name = {r.tool_name: r for r in rows}
        items: list[dict] = []
        for name in TOOL_CATALOG:
            row = by_name.get(name)
            if row is None:
                for legacy in TOOL_CATALOG[name].get("legacy_keys") or ():
                    row = by_name.get(legacy)
                    if row is not None:
                        break
            items.append(self.to_safe_dict(name, row))
        return items

    async def get_row(
        self, db: AsyncSession, tenant_id: UUID, tool_name: str
    ) -> ToolConfig | None:
        """读取单条库记录；新名未命中时回退旧工具名。"""
        canonical = normalize_tool_name(tool_name)
        result = await db.execute(
            select(ToolConfig).where(
                ToolConfig.tenant_id == tenant_id,
                ToolConfig.tool_name == canonical,
            )
        )
        row = result.scalars().first()
        if row is not None:
            return row
        legacy_keys = (TOOL_CATALOG.get(canonical) or {}).get("legacy_keys") or ()
        for legacy in legacy_keys:
            result = await db.execute(
                select(ToolConfig).where(
                    ToolConfig.tenant_id == tenant_id,
                    ToolConfig.tool_name == legacy,
                )
            )
            row = result.scalars().first()
            if row is not None:
                return row
        return None

    async def upsert(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        tool_name: str,
        data: dict[str, Any],
    ) -> ToolConfig:
        """新增或更新。api_key 缺省/占位则保留原密文。"""
        tool_name = normalize_tool_name(tool_name)
        if tool_name not in TOOL_CATALOG:
            raise BusinessError(f"未知工具：{tool_name}", code="UNKNOWN_TOOL")
        meta = TOOL_CATALOG[tool_name]
        provider = data.get("provider") or "bocha"
        if provider not in (meta.get("providers") or {}):
            raise BusinessError(f"工具不支持该提供商：{provider}", code="UNKNOWN_PROVIDER")

        existing = await self.get_row(db, tenant_id, tool_name)
        extra = {
            "timeout_seconds": int(data.get("timeout_seconds") or 15),
            "max_results": int(data.get("max_results") or 16),
            "fetch_pages": int(data.get("fetch_pages") or 0),
            "fetch_max_chars": int(data.get("fetch_max_chars") or 4000),
        }
        raw_key = data.get("api_key")
        if existing:
            # 统一写回规范工具名，逐步迁移旧 key
            existing.tool_name = tool_name
            existing.provider = provider
            existing.base_url = data.get("base_url")
            existing.enabled = bool(data.get("enabled", existing.enabled))
            existing.extra_params = extra
            if not is_placeholder_api_key(raw_key):
                existing.api_key_encrypted = encrypt_field(str(raw_key).strip())
            cfg = existing
        else:
            cfg = ToolConfig(
                tenant_id=tenant_id,
                tool_name=tool_name,
                provider=provider,
                base_url=data.get("base_url"),
                enabled=bool(data.get("enabled", False)),
                extra_params=extra,
                api_key_encrypted=(
                    encrypt_field(str(raw_key).strip())
                    if not is_placeholder_api_key(raw_key)
                    else None
                ),
            )
            db.add(cfg)

        try:
            await db.commit()
        except ProgrammingError as exc:
            await db.rollback()
            if _is_missing_tool_table(exc):
                raise BusinessError(
                    "尚未创建 tool_configs 表，请在 backend 目录执行 alembic upgrade head",
                    code="MIGRATION_REQUIRED",
                )
            raise
        await db.refresh(cfg)
        self._invalidate_cache(tenant_id, tool_name)
        self._invalidate_cache(tenant_id, TOOL_SEARCH_OFFICIAL_POLICY_LEGACY)
        return cfg

    async def resolve_web_search(
        self, db: AsyncSession, tenant_id: UUID
    ) -> WebSearchRuntime:
        """权威检索运行时配置：有库记录则覆盖 env，Key 缺失时仍可用 env。"""
        cache_key = (str(tenant_id), TOOL_SEARCH_OFFICIAL_DATA)
        now = time.time()
        cached = _config_cache.get(cache_key)
        if cached and (now - _cache_timestamps.get(cache_key, 0)) < _CACHE_TTL_SECONDS:
            return cached

        base = WebSearchRuntime.from_settings()
        row = await self.get_row(db, tenant_id, TOOL_SEARCH_OFFICIAL_DATA)
        runtime = self._merge_web_search(base, row)
        _config_cache[cache_key] = runtime
        _cache_timestamps[cache_key] = now
        return runtime

    def runtime_from_payload(
        self, payload: dict[str, Any], stored_key: str = ""
    ) -> WebSearchRuntime:
        """测试连通性：表单值 + 已存 Key。"""
        base = WebSearchRuntime.from_settings()
        provider = payload.get("provider") or base.provider
        if provider not in ("bocha", "tavily"):
            provider = base.provider
        typed: SearchProvider = provider
        extra = payload
        key = (payload.get("api_key") or "").strip()
        if is_placeholder_api_key(key):
            key = stored_key or base.api_key
        return WebSearchRuntime(
            enabled=True,
            provider=typed,
            api_key=key,
            base_url=(payload.get("base_url") or "").strip() or base.base_url,
            timeout=int(extra.get("timeout_seconds") or base.timeout),
            max_results=int(extra.get("max_results") or base.max_results),
            fetch_pages=int(extra.get("fetch_pages") or 0),
            fetch_max_chars=int(extra.get("fetch_max_chars") or base.fetch_max_chars),
        )

    def to_safe_dict(self, tool_name: str, cfg: ToolConfig | None) -> dict:
        """返回给前端的安全视图，不含明文 Key。"""
        meta = TOOL_CATALOG[tool_name]
        env_rt = WebSearchRuntime.from_settings()
        extra = (cfg.extra_params if cfg and isinstance(cfg.extra_params, dict) else {}) or {}
        plain = ""
        if cfg and cfg.api_key_encrypted:
            try:
                plain = decrypt_field(cfg.api_key_encrypted)
            except Exception:
                logger.warning("tool config decrypt failed tool=%s", tool_name)
        elif env_rt.api_key:
            plain = env_rt.api_key
        return {
            "id": str(cfg.id) if cfg else None,
            "tool_name": tool_name,
            "label": meta["label"],
            "description": meta["description"],
            "provider": (cfg.provider if cfg else None) or env_rt.provider,
            "base_url": (cfg.base_url if cfg else None) or env_rt.base_url or None,
            "enabled": cfg.enabled if cfg is not None else env_rt.enabled,
            "timeout_seconds": int(extra.get("timeout_seconds") or env_rt.timeout),
            "max_results": int(extra.get("max_results") or env_rt.max_results),
            "fetch_pages": int(extra.get("fetch_pages") or env_rt.fetch_pages),
            "fetch_max_chars": int(extra.get("fetch_max_chars") or env_rt.fetch_max_chars),
            "has_api_key": bool(plain),
            "api_key_masked": mask_api_key(plain),
            "source": "db" if cfg is not None else "env",
            "updated_at": cfg.updated_at.isoformat() if cfg and cfg.updated_at else None,
        }

    def _merge_web_search(
        self, base: WebSearchRuntime, row: ToolConfig | None
    ) -> WebSearchRuntime:
        """库记录覆盖开关/提供商；Key 优先用库，没有则用 env。"""
        if row is None:
            return base
        extra = row.extra_params if isinstance(row.extra_params, dict) else {}
        provider = row.provider or base.provider
        if provider not in ("bocha", "tavily"):
            provider = base.provider
        typed: SearchProvider = provider
        key = base.api_key
        if row.api_key_encrypted:
            try:
                decrypted = decrypt_field(row.api_key_encrypted).strip()
                if decrypted:
                    key = decrypted
            except Exception:
                logger.exception("decrypt tool api key failed")
        return WebSearchRuntime(
            enabled=bool(row.enabled),
            provider=typed,
            api_key=key,
            base_url=(row.base_url or "").strip() or base.base_url,
            timeout=int(extra.get("timeout_seconds") or base.timeout),
            max_results=int(extra.get("max_results") or base.max_results),
            fetch_pages=int(extra.get("fetch_pages") if extra.get("fetch_pages") is not None else base.fetch_pages),
            fetch_max_chars=int(extra.get("fetch_max_chars") or base.fetch_max_chars),
        )

    async def _list_rows(self, db: AsyncSession, tenant_id: UUID) -> list[ToolConfig]:
        result = await db.execute(
            select(ToolConfig).where(ToolConfig.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    @staticmethod
    def _invalidate_cache(tenant_id: UUID, tool_name: str) -> None:
        _config_cache.pop((str(tenant_id), tool_name), None)
        _cache_timestamps.pop((str(tenant_id), tool_name), None)


tool_config_service = ToolConfigService()
