"""Operational metrics for /metrics/summary (what you alert on).

Backed by Redis so counters/latencies survive across worker+backend processes:
  metrics:cache:hits / :misses     -> cache hit rate
  metrics:latencies (capped list)  -> p50/p95/p99 end-to-end latency
Queue depth and indexing backlog are read live from Redis/Postgres.
"""

from __future__ import annotations

import logging

import redis as sync_redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.document import Document
from app.models.enums import DocumentStatus

logger = logging.getLogger("rag.metrics")
_settings = get_settings()

_LAT_KEY = "metrics:latencies"
_HITS = "metrics:cache:hits"
_MISSES = "metrics:cache:misses"
_MAX_LATENCIES = 1000


def _redis() -> sync_redis.Redis:
    return sync_redis.from_url(_settings.redis_url, decode_responses=True)


def record_cache(hit: bool) -> None:
    try:
        _redis().incr(_HITS if hit else _MISSES)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache metric failed: %s", exc)


def record_latency(ms: float) -> None:
    try:
        r = _redis()
        r.lpush(_LAT_KEY, ms)
        r.ltrim(_LAT_KEY, 0, _MAX_LATENCIES - 1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("latency metric failed: %s", exc)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(round(p * (len(values) - 1))))
    return round(values[idx], 1)


async def summary(db: AsyncSession) -> dict:
    r = _redis()
    try:
        lats = [float(x) for x in r.lrange(_LAT_KEY, 0, -1)]
        hits = int(r.get(_HITS) or 0)
        misses = int(r.get(_MISSES) or 0)
        queue_depth = int(r.llen(_settings.ingest_queue)) + int(r.llen(_settings.eval_queue))
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics redis read failed: %s", exc)
        lats, hits, misses, queue_depth = [], 0, 0, 0

    backlog = (
        await db.execute(
            select(func.count(Document.id)).where(
                Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING])
            )
        )
    ).scalar_one()

    total = hits + misses
    return {
        "queue_depth": queue_depth,
        "vllm_queue_wait_ms": 0,  # dev: Ollama; prod scrapes vLLM /metrics
        "indexing_backlog": int(backlog),
        "cache_hit_rate": round(hits / total, 3) if total else 0.0,
        "latency_ms": {
            "p50": _percentile(lats, 0.50),
            "p95": _percentile(lats, 0.95),
            "p99": _percentile(lats, 0.99),
        },
    }
