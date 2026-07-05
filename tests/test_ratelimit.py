"""Quota DoD: per-user request-rate + in-flight concurrency limits trip at 429."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.core import ratelimit

_settings = get_settings()


async def test_requests_per_minute_limit_trips():
    uid = uuid.uuid4()
    for _ in range(_settings.per_user_requests_per_min):
        await ratelimit.check_request_rate(uid)  # within budget
    with pytest.raises(HTTPException) as exc:
        await ratelimit.check_request_rate(uid)
    assert exc.value.status_code == 429


async def test_inflight_concurrency_cap_and_release():
    uid = uuid.uuid4()
    for _ in range(_settings.per_user_max_inflight):
        await ratelimit.acquire_inflight(uid)
    with pytest.raises(HTTPException) as exc:
        await ratelimit.acquire_inflight(uid)
    assert exc.value.status_code == 429

    # Releasing a slot lets the next request through.
    await ratelimit.release_inflight(uid)
    await ratelimit.acquire_inflight(uid)
    await ratelimit.release_inflight(uid)


async def test_global_admission_cap_and_release(monkeypatch):
    from app.core.redis import get_redis

    # Small cap for a fast test; clear any residual global counter first.
    monkeypatch.setattr(_settings, "global_max_inflight", 3)
    await get_redis().delete(ratelimit._GLOBAL_INFLIGHT)

    for _ in range(3):
        await ratelimit.acquire_global_slot()
    with pytest.raises(HTTPException) as exc:
        await ratelimit.acquire_global_slot()
    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") == "5"

    # Releasing a global slot re-opens capacity.
    await ratelimit.release_global_slot()
    await ratelimit.acquire_global_slot()
    for _ in range(3):
        await ratelimit.release_global_slot()


async def test_global_cap_rejection_frees_per_user_slot(monkeypatch):
    """A global-cap 429 must not leak the caller's per-user in-flight slot."""
    from app.core.redis import get_redis
    from app.models.user import User

    monkeypatch.setattr(_settings, "global_max_inflight", 0)  # always saturated
    r = get_redis()
    await r.delete(ratelimit._GLOBAL_INFLIGHT)
    uid = uuid.uuid4()

    # Drive the FastAPI dependency generator directly; it must raise 429.
    agen = ratelimit.rate_limit(User(id=uid, email="x@y.z", hashed_password="x"))
    with pytest.raises(HTTPException) as exc:
        await agen.__anext__()
    assert exc.value.status_code == 429
    # The per-user in-flight counter must be back to 0 (slot released on reject).
    assert int(await r.get(f"quota:inflight:{uid}") or 0) == 0
