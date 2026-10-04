"""可选 Langfuse 观测：无密钥或未安装 SDK 时为零开销空操作。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_ATTR = 200
_client: Any = None
_client_tried = False


def is_enabled() -> bool:
    """同时有公钥和私钥才上报。"""
    try:
        from app.config import get_settings

        settings = get_settings()
    except Exception:
        return False
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def _safe_attrs(data: dict[str, Any]) -> dict[str, Any]:
    """截断字符串，避免把票据全文送进观测。"""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str):
            out[key] = value[:_MAX_ATTR]
        elif isinstance(value, (int, float, bool)):
            out[key] = value
        else:
            out[key] = str(value)[:_MAX_ATTR]
    return out


def _get_client() -> Any:
    """懒加载 Langfuse；失败后本进程不再重试。"""
    global _client, _client_tried
    if not is_enabled():
        return None
    if _client_tried:
        return _client
    _client_tried = True
    try:
        from langfuse import Langfuse

        from app.config import get_settings

        settings = get_settings()
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or None,
        )
    except Exception:
        logger.info("langfuse unavailable, observe disabled")
        _client = None
    return _client


def record(name: str, **attrs: Any) -> None:
    """记一条决策事件；关闭时只走 structlog。"""
    payload = _safe_attrs(attrs)
    logger.info("agent.observe event=%s attrs=%s", name, payload)
    client = _get_client()
    if client is None:
        return
    try:
        if hasattr(client, "event"):
            client.event(name=name, metadata=payload)
        elif hasattr(client, "create_event"):
            client.create_event(name=name, metadata=payload)
    except Exception:
        logger.debug("langfuse event failed name=%s", name, exc_info=True)


def reset_for_tests() -> None:
    """单测重置客户端缓存。"""
    global _client, _client_tried
    _client = None
    _client_tried = False
