"""Phase 2 ingest-job tracking: Postgres progress rows, retry accounting,
dead-letter queue + requeue. (Spec task 6 — queue-driven workers.)"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.ingestion import jobs
from app.models.collection import Collection
from app.models.department import Department
from app.models.document import Document
from app.models.enums import DocumentStatus, IngestStatus
from app.models.ingest import IngestJob
from app.queue import sync_client

_settings = get_settings()


# ----------------------------------------------------------------- API layer
async def test_upload_creates_queued_job(client, seed, login, sessionmaker):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    r = await client.post(
        "/documents/upload",
        headers=headers,
        data={"collection_id": str(seed["coll_a"])},
        files={"file": ("notes.txt", b"Phase 2 job tracking test content.")},
    )
    assert r.status_code == 201, r.text
    doc_id = uuid.UUID(r.json()["document"]["id"])

    async with sessionmaker() as db:
        rows = (await db.execute(
            select(IngestJob).where(IngestJob.document_id == doc_id)
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == IngestStatus.QUEUED
    assert rows[0].attempt == 0


# ------------------------------------------------------------- worker helpers
@pytest.fixture
def doc_row(sync_session):
    dept = Department(name=f"D-{uuid.uuid4().hex[:6]}")
    sync_session.add(dept)
    sync_session.flush()
    coll = Collection(name=f"C-{uuid.uuid4().hex[:6]}", department_id=dept.id)
    sync_session.add(coll)
    sync_session.flush()
    doc = Document(collection_id=coll.id, filename="x.txt", file_type="txt",
                   content_hash=uuid.uuid4().hex, status=DocumentStatus.PENDING)
    sync_session.add(doc)
    sync_session.commit()
    return doc


def test_job_lifecycle_success(sync_session, doc_row):
    job_id = jobs.job_started(sync_session, None, str(doc_row.id), attempt=0)
    job = sync_session.get(IngestJob, job_id)
    assert job.status == IngestStatus.PARSING and job.started_at is not None

    jobs.job_stage(sync_session, job_id, IngestStatus.INDEXING)
    assert sync_session.get(IngestJob, job_id).status == IngestStatus.INDEXING

    jobs.job_finished(sync_session, job_id)
    job = sync_session.get(IngestJob, job_id)
    assert job.status == IngestStatus.INDEXED
    assert job.finished_at is not None and job.error is None


def test_job_retry_reuses_row_then_fails(sync_session, doc_row):
    job_id = jobs.job_started(sync_session, None, str(doc_row.id), attempt=0)
    jobs.job_finished(sync_session, job_id, error="boom", requeued=True)
    job = sync_session.get(IngestJob, job_id)
    assert job.status == IngestStatus.QUEUED and job.error == "boom"

    # Retry consumes the same row (payload carries job_id).
    again = jobs.job_started(sync_session, str(job_id), str(doc_row.id), attempt=1)
    assert again == job_id
    job = sync_session.get(IngestJob, job_id)
    assert job.status == IngestStatus.PARSING and job.attempt == 1 and job.error is None

    jobs.job_finished(sync_session, job_id, error="boom again", requeued=False)
    job = sync_session.get(IngestJob, job_id)
    assert job.status == IngestStatus.FAILED and "boom again" in job.error


def test_job_started_for_deleted_document_raises_document_gone(sync_session):
    """Regression: a stale queue payload for a deleted document crashed the
    worker with an FK violation. It must raise DocumentGone (job dropped)."""
    with pytest.raises(jobs.DocumentGone):
        jobs.job_started(sync_session, None, str(uuid.uuid4()), attempt=0)


# ---------------------------------------------------------------- dead letter
@pytest.fixture
def isolated_queues(monkeypatch):
    """Point queue names away from the live worker's lists and clean up."""
    monkeypatch.setattr(_settings, "ingest_queue", "test:ingest:queue")
    monkeypatch.setattr(_settings, "ingest_dlq", "test:ingest:dlq")
    client = sync_client()
    client.delete("test:ingest:queue", "test:ingest:dlq")
    yield client
    client.delete("test:ingest:queue", "test:ingest:dlq")


def test_dlq_push_inspect_requeue(isolated_queues):
    client = isolated_queues
    payload = {"document_id": str(uuid.uuid4()), "attempt": 2,
               "job_id": str(uuid.uuid4())}
    jobs.push_dlq(client, payload, error="parser exploded")

    entries = jobs.dlq_entries(client)
    assert len(entries) == 1
    assert entries[0]["error"] == "parser exploded"
    assert entries[0]["failed_at"]

    moved = jobs.requeue_dlq(client)
    assert moved == 1
    assert client.llen("test:ingest:dlq") == 0
    assert client.llen("test:ingest:queue") == 1
    import json
    requeued = json.loads(client.lindex("test:ingest:queue", 0))
    # Full retry budget restored; job row identity preserved.
    assert requeued["attempt"] == 0
    assert requeued["job_id"] == payload["job_id"]
