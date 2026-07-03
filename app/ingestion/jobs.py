"""Ingest-job progress tracking + dead-letter handling (Phase 2 spec task 6).

The queue itself stays the existing Redis list (BLPOP worker) — extending it
was chosen over an arq/rq rewrite (see docs/CHANGELOG.md Phase 2): the spec's
requirements are properties (idempotent, resumable, DLQ, Postgres progress),
all satisfiable surgically on the KEEP worker.

- API enqueue creates a QUEUED `ingest_jobs` row and puts its id in the payload.
- The worker advances the row through PARSING → (CAPTIONING) → INDEXING →
  INDEXED/FAILED; retries reuse the row (attempt++).
- Permanent failures push the full payload + error to the `ingest:dlq` Redis
  list; `requeue_dlq()` drains it back onto the queue (admin-triggered).

Resumability: indexing is idempotent per doc_id + content_hash (clear-then-write
in both Postgres and Qdrant), so a resume is simply a re-enqueue.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import redis as sync_redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import IngestStatus
from app.models.ingest import IngestJob

_settings = get_settings()


# ------------------------------------------------------------- async (API side)
async def create_job(db: AsyncSession, document_id: uuid.UUID) -> IngestJob:
    """New QUEUED row per API-triggered ingest (upload / re-ingest button)."""
    job = IngestJob(document_id=document_id, status=IngestStatus.QUEUED, attempt=0)
    db.add(job)
    await db.flush()
    return job


async def latest_job(db: AsyncSession, document_id: uuid.UUID) -> IngestJob | None:
    rows = await db.execute(
        select(IngestJob).where(IngestJob.document_id == document_id)
        .order_by(IngestJob.created_at.desc()).limit(1)
    )
    return rows.scalar_one_or_none()


# -------------------------------------------------------------- sync (worker side)
def _get_or_create(db: Session, job_id: str | None, document_id: str) -> IngestJob:
    if job_id:
        job = db.get(IngestJob, uuid.UUID(job_id))
        if job is not None:
            return job
    # Payload predates job tracking (or row was pruned) — track from here.
    job = IngestJob(document_id=uuid.UUID(document_id),
                    status=IngestStatus.QUEUED, attempt=0)
    db.add(job)
    db.flush()
    return job


def job_started(db: Session, job_id: str | None, document_id: str,
                attempt: int) -> uuid.UUID:
    job = _get_or_create(db, job_id, document_id)
    job.status = IngestStatus.PARSING
    job.attempt = attempt
    job.error = None
    job.started_at = datetime.now(timezone.utc)
    job.finished_at = None
    db.commit()
    return job.id


def job_stage(db: Session, job_id: uuid.UUID, status: IngestStatus) -> None:
    job = db.get(IngestJob, job_id)
    if job is not None:
        job.status = status
        db.commit()


def job_finished(db: Session, job_id: uuid.UUID, *, error: str | None = None,
                 requeued: bool = False) -> None:
    job = db.get(IngestJob, job_id)
    if job is None:
        return
    if error is None:
        job.status = IngestStatus.INDEXED
    elif requeued:
        job.status = IngestStatus.QUEUED  # retry pending; keep error for display
        job.error = error[:2000]
    else:
        job.status = IngestStatus.FAILED
        job.error = error[:2000]
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


# --------------------------------------------------------------------- dead letter
def push_dlq(client: sync_redis.Redis, payload: dict, error: str) -> None:
    entry = {**payload, "error": error[:2000],
             "failed_at": datetime.now(timezone.utc).isoformat()}
    client.rpush(_settings.ingest_dlq, json.dumps(entry))


def dlq_entries(client: sync_redis.Redis, limit: int = 100) -> list[dict]:
    return [json.loads(x) for x in client.lrange(_settings.ingest_dlq, 0, limit - 1)]


def requeue_dlq(client: sync_redis.Redis, limit: int = 100) -> int:
    """Drain up to `limit` dead letters back onto the ingest queue (attempt
    counter reset so the document gets a full retry budget). Returns count."""
    n = 0
    for _ in range(limit):
        raw = client.lpop(_settings.ingest_dlq)
        if raw is None:
            break
        entry = json.loads(raw)
        client.rpush(_settings.ingest_queue, json.dumps({
            "document_id": entry["document_id"],
            "attempt": 0,
            "job_id": entry.get("job_id"),
        }))
        n += 1
    return n
