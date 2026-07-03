"""Redis-backed ingestion job queue.

Job payload: {"document_id": "...", "attempt": N, "job_id": "..."} — job_id
references the `ingest_jobs` progress row (Phase 2). The API enqueues (async);
the worker consumes (sync, blocking pop).
"""

from __future__ import annotations

import json
import uuid

import redis as sync_redis

from app.config import get_settings
from app.core.redis import get_redis

_settings = get_settings()


async def enqueue_index(document_id: uuid.UUID, attempt: int = 0,
                        job_id: uuid.UUID | None = None) -> None:
    client = get_redis()
    await client.rpush(
        _settings.ingest_queue,
        json.dumps({"document_id": str(document_id), "attempt": attempt,
                    "job_id": str(job_id) if job_id else None}),
    )


def sync_client() -> sync_redis.Redis:
    return sync_redis.from_url(_settings.redis_url, decode_responses=True)


def enqueue_index_sync(client: sync_redis.Redis, document_id: str, attempt: int,
                       job_id: str | None = None) -> None:
    client.rpush(
        _settings.ingest_queue,
        json.dumps({"document_id": document_id, "attempt": attempt, "job_id": job_id}),
    )
