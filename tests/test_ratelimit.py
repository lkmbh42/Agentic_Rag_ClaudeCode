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
