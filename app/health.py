"""Health and readiness endpoints.

- /health        liveness: the process is up. Used by the Docker healthcheck so
                 the container reports healthy as soon as uvicorn serves, without
                 flapping while dependencies finish booting.
- /health/ready  readiness: dependencies (Postgres, Redis, Qdrant) are reachable.
                 Used for orchestration / smoke tests, not the container healthcheck.

Dependency checks are best-effort and time-bounded; a slow dependency must never
hang the endpoint.
"""

from __future__ import annotations

import asyncio
import socket

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


def _tcp_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    """Cheap reachability probe — a real client check lands when each subsystem
    is implemented (Postgres in Phase 2, Qdrant in Phase 4)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "backend", "version": __version__}


@router.get("/health/ready")
async def ready() -> JSONResponse:
    s = get_settings()
    checks = await asyncio.gather(
        asyncio.to_thread(_tcp_ok, s.postgres_host, s.postgres_port),
        asyncio.to_thread(_tcp_ok, s.redis_host, s.redis_port),
        asyncio.to_thread(_tcp_ok, s.qdrant_host, s.qdrant_http_port),
    )
    result = {
        "postgres": checks[0],
        "redis": checks[1],
        "qdrant": checks[2],
    }
    all_ok = all(result.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "dependencies": result},
    )
