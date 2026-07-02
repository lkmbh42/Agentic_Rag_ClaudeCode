"""Redis client + JWT jti denylist.

Revocation strategy: when a token is revoked (logout, refresh rotation, admin
suspend/revoke-sessions), its jti is stored with a TTL equal to the token's
remaining lifetime, so the key self-expires exactly when the token would.

Availability note: the denylist *check* fails OPEN (treats unknown as
not-revoked) and logs a warning if Redis is unreachable. Access tokens are
short-lived (15 min), which bounds the exposure window; we prefer auth
availability over hard-failing every request when Redis blips. Writes (revoke)
fail loud so the caller knows revocation did not take effect.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("rag.redis")

_DENYLIST_PREFIX = "jwt:denylist:"
_EPOCH_PREFIX = "user:session_epoch:"


@lru_cache
def get_redis() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Add a token's jti to the denylist for its remaining lifetime."""
    if ttl_seconds <= 0:
        return
    client = get_redis()
    await client.set(f"{_DENYLIST_PREFIX}{jti}", "1", ex=ttl_seconds)


async def is_revoked(jti: str) -> bool:
    client = get_redis()
    try:
        return await client.exists(f"{_DENYLIST_PREFIX}{jti}") == 1
    except Exception as exc:  # noqa: BLE001 - availability over strictness
        logger.warning("denylist check failed (failing open): %s", exc)
        return False


async def bump_session_epoch(user_id) -> None:
    """Invalidate ALL of a user's existing tokens (issued-before-now) at once.
    Used for admin revoke-sessions / suspend / credential reset. Float seconds so
    a token whose integer `iat` falls in the same second as the bump is still
    invalidated (epoch > iat)."""
    await get_redis().set(f"{_EPOCH_PREFIX}{user_id}", repr(time.time()))


async def session_epoch(user_id) -> float:
    try:
        val = await get_redis().get(f"{_EPOCH_PREFIX}{user_id}")
        return float(val) if val else 0.0
    except Exception as exc:  # noqa: BLE001 - fail open
        logger.warning("session epoch read failed: %s", exc)
        return 0.0
