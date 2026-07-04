"""FastAPI application entrypoint.

Phase 1 scope: a runnable, health-reporting backend with the cross-cutting
middleware/observability seams stubbed so later phases drop in without
restructuring. Auth, RBAC, documents, chat, and the agent graph arrive in
Phases 2+.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

from app import __version__
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.collections import router as collections_router
from app.api.documents import router as documents_router
from app.api.media import router as media_router
from app.api.search import router as search_router
from app.config import get_settings
from app.core.deps import require_admin
from app.db.session import engine
from app.health import router as health_router

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger("rag.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("backend starting env=%s llm=%s", settings.app_env, settings.llm_base_url)
    from app.observability.tracing import setup_tracing

    setup_tracing()
    yield
    # Dispose the connection pool cleanly on shutdown.
    await engine.dispose()
    logger.info("backend shutting down")


app = FastAPI(
    title="Agentic RAG Platform",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(collections_router)
app.include_router(documents_router)
app.include_router(media_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "agentic-rag-backend",
        "version": __version__,
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus exposition. Operational gauges (queue depth, vLLM queue wait,
    indexing backlog, cache hit rate, latency percentiles) are registered as
    they come online in Phase 7."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/metrics/summary", dependencies=[Depends(require_admin)])
async def metrics_summary(db: AsyncSession = Depends(get_db)) -> dict:
    """Live-ops rollup: queue depth, vLLM queue wait, indexing backlog, cache hit
    rate, and p50/p95/p99 end-to-end latency. This is what the admin dashboard
    surfaces and what alerts fire on. Admin-only: operational internals must not
    be readable anonymously (Prometheus /metrics is protected at network level)."""
    from app.observability import metrics

    return await metrics.summary(db)
