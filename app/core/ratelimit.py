"""Per-user rate limiting + concurrency quotas (API-layer abuse/overload guard).

Circuit breakers (Phase 5) bound a single request's work; these quotas stop one
user from flooding the queue:
  - requests-per-minute: fixed-window counter, returns 429 when exceeded;
  - in-flight concurrency: a live counter incremented on entry / decremented on
    exit, returns 429 when the user already has too many requests running.

Backed by Redis so the limits hold across all backend replicas.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status

from app.config import get_settings
from app.core.deps import get_current_user
from app.core.redis import get_redis
from app.models.user import User

_settings = get_settings()

_INFLIGHT_TTL = 300  # safety expiry so a crash can't leak a slot forever


async def check_request_rate(user_id: uuid.UUID) -> None:
    client = get_redis()
    window = int(time.time() // 60)
    key = f"quota:rpm:{user_id}:{window}"
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, 70)
    if count > _settings.per_user_requests_per_min:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded (requests per minute)",
        )


async def acquire_inflight(user_id: uuid.UUID) -> None:
    client = get_redis()
    key = f"quota:inflight:{user_id}"
    current = await client.incr(key)
    await client.expire(key, _INFLIGHT_TTL)
    if current > _settings.per_user_max_inflight:
        await client.decr(key)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent requests",
        )


async def release_inflight(user_id: uuid.UUID) -> None:
    client = get_redis()
    key = f"quota:inflight:{user_id}"
    # Never let the counter go negative.
    if await client.decr(key) < 0:
        await client.set(key, 0)


_GLOBAL_INFLIGHT = "admission:inflight:global"


async def acquire_global_slot() -> None:
    """Global admission control (Phase 5): bound concurrent in-flight turns
    across ALL users so a burst can't overrun the vLLM queue. Friendly 429 with
    Retry-After when the system is saturated."""
    client = get_redis()
    current = await client.incr(_GLOBAL_INFLIGHT)
    await client.expire(_GLOBAL_INFLIGHT, _INFLIGHT_TTL)
    if current > _settings.global_max_inflight:
        await client.decr(_GLOBAL_INFLIGHT)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The assistant is at capacity right now — please retry in a moment.",
            headers={"Retry-After": "5"},
        )


async def release_global_slot() -> None:
    client = get_redis()
    if await client.decr(_GLOBAL_INFLIGHT) < 0:
        await client.set(_GLOBAL_INFLIGHT, 0)


async def rate_limit(user: User = Depends(get_current_user)) -> AsyncIterator[User]:
    """FastAPI dependency: enforce per-user quotas AND global admission control,
    releasing both slots on exit. Order matters — the global slot is acquired
    last and released first so a global-cap rejection never consumes a per-user
    slot, and neither slot leaks on the 429 path."""
    await check_request_rate(user.id)
    await acquire_inflight(user.id)
    try:
        await acquire_global_slot()
    except HTTPException:
        await release_inflight(user.id)
        raise
    try:
        yield user
    finally:
        await release_global_slot()
        await release_inflight(user.id)
