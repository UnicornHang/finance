"""请求限流：优先 Redis 滑动窗口，不可用时退回进程内计数。"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Annotated

from fastapi import Depends, Request

from app.config import settings
from app.core.exceptions import RateLimitError
from app.deps import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

_MEMORY: dict[str, tuple[int, float]] = {}
_MEMORY_LOCK = Lock()
_redis = None
_redis_failed = False


def parse_limit(spec: str) -> tuple[int, int]:
    """解析 ``100/minute`` → (次数, 窗口秒数)。"""
    raw = (spec or "").strip().lower()
    if not raw or "/" not in raw:
        return 100, 60
    count_s, unit = raw.split("/", 1)
    try:
        count = max(1, int(count_s.strip()))
    except ValueError:
        count = 100
    unit = unit.strip()
    if unit in ("s", "sec", "second", "seconds"):
        return count, 1
    if unit in ("m", "min", "minute", "minutes"):
        return count, 60
    if unit in ("h", "hour", "hours"):
        return count, 3600
    if unit in ("d", "day", "days"):
        return count, 86400
    return count, 60


def _get_redis():
    """懒连接 Redis；失败则标记并退回内存。"""
    global _redis, _redis_failed
    if _redis_failed:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url or "redis://localhost:6379/0",
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            decode_responses=True,
        )
        client.ping()
        _redis = client
        return _redis
    except Exception:
        _redis_failed = True
        logger.warning("rate_limit redis unavailable, using in-memory counters")
        return None


def _hit_memory(key: str, limit: int, window_sec: int) -> bool:
    """进程内固定窗口；超限返回 True。"""
    now = time.time()
    with _MEMORY_LOCK:
        count, start = _MEMORY.get(key, (0, now))
        if now - start >= window_sec:
            count, start = 0, now
        count += 1
        _MEMORY[key] = (count, start)
        return count > limit


def _hit_redis(key: str, limit: int, window_sec: int) -> bool:
    """Redis INCR + EXPIRE 固定窗口；超限返回 True。"""
    client = _get_redis()
    if client is None:
        return _hit_memory(key, limit, window_sec)
    try:
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_sec, nx=True)
        count, _ = pipe.execute()
        return int(count) > limit
    except Exception:
        logger.warning("rate_limit redis error, fallback memory", exc_info=True)
        return _hit_memory(key, limit, window_sec)


def check_limits(*, user_id: str | None, tenant_id: str | None, ip: str | None) -> None:
    """按用户 / 租户 / IP 依次检查，任一超限抛 RateLimitError。"""
    checks: list[tuple[str, str, str]] = []
    if user_id:
        checks.append(
            (f"rl:user:{user_id}", settings.rate_limit_per_user, "用户")
        )
    if tenant_id:
        checks.append(
            (f"rl:tenant:{tenant_id}", settings.rate_limit_per_tenant, "租户")
        )
    if ip:
        checks.append((f"rl:ip:{ip}", settings.rate_limit_per_ip, "IP"))

    for key, spec, label in checks:
        limit, window = parse_limit(spec)
        if _hit_redis(key, limit, window):
            raise RateLimitError(f"请求过于频繁（{label}限流），请稍后再试")


def client_ip(request: Request) -> str:
    """取客户端 IP，优先 X-Forwarded-For 首段。"""
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


async def enforce_rate_limit(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """需登录的高成本接口限流依赖；通过后原样返回 user。"""
    check_limits(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        ip=client_ip(request),
    )
    return user
