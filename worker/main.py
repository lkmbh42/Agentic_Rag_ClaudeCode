"""Background worker: consumes the ingestion queue and indexes documents.

- Blocking pop from the Redis ingest queue (also refreshes the liveness
  heartbeat each idle tick so the Docker healthcheck stays green).
- On failure, re-enqueues with an incremented attempt up to MAX_INDEXING_RETRIES,
  then leaves the document in FAILED status (set by the indexer).
- The async evaluation consumer (Phase 7) attaches to this same loop later.

Liveness: the worker has no HTTP port, so it writes a heartbeat file whose mtime
the container healthcheck checks for freshness.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
import uuid

from app.config import get_settings
from app.db.sync_session import SyncSessionLocal
from app.eval.runner import default_chat_fn, persist_eval, score_payload
from app.ingestion import jobs
from app.ingestion.indexer import index_document
from app.ingestion.qdrant_index import QdrantIndex
from app.models.enums import IngestStatus
from app.observability.tracing import record_eval, setup_tracing
from app.queue import enqueue_index_sync, sync_client
from app.retrieval.factory import get_embedder

HEARTBEAT_PATH = os.environ.get("WORKER_HEARTBEAT_PATH", "/tmp/worker_heartbeat")
BLOCK_TIMEOUT = 5

_settings = get_settings()
logging.basicConfig(level=_settings.log_level)
logger = logging.getLogger("rag.worker")

_running = True


def _stop(signum, _frame) -> None:
    global _running
    logger.info("worker received signal %s, stopping", signum)
    _running = False


def _touch_heartbeat() -> None:
    with open(HEARTBEAT_PATH, "w") as fh:
        fh.write(str(time.time()))


def _handle_job(payload: str, redis_client, embedder, qindex: QdrantIndex) -> None:
    job = json.loads(payload)
    document_id = job["document_id"]
    attempt = int(job.get("attempt", 0))
    with SyncSessionLocal() as db:
        try:
            job_id = jobs.job_started(db, job.get("job_id"), document_id, attempt)
        except jobs.DocumentGone:
            logger.warning("dropping stale job for deleted document %s", document_id)
            return
        except Exception as exc:  # noqa: BLE001 - tracking must never kill the loop
            logger.error("job tracking failed for %s: %s — continuing untracked",
                         document_id, exc)
            db.rollback()
            job_id = None

        def _stage(name: str) -> None:
            # Progress row + heartbeat: long stages must not stale the healthcheck.
            _touch_heartbeat()
            if job_id is not None:
                jobs.job_stage(db, job_id, IngestStatus(name))

        try:
            count = index_document(db, uuid.UUID(document_id), embedder=embedder,
                                   qindex=qindex, on_stage=_stage)
            if job_id is not None:
                jobs.job_finished(db, job_id)
            logger.info("indexed %s (%d chunks, attempt %d)", document_id, count, attempt)
        except Exception as exc:  # noqa: BLE001
            will_retry = attempt + 1 < _settings.max_indexing_retries
            if job_id is not None:
                jobs.job_finished(db, job_id, error=str(exc), requeued=will_retry)
            job_ref = str(job_id) if job_id is not None else None
            if will_retry:
                logger.warning("index failed %s (attempt %d): %s — requeueing",
                               document_id, attempt, exc)
                enqueue_index_sync(redis_client, document_id, attempt + 1,
                                   job_id=job_ref)
            else:
                logger.error("index permanently failed %s after %d attempts: %s — dead-lettered",
                             document_id, attempt + 1, exc)
                jobs.push_dlq(redis_client,
                              {"document_id": document_id, "attempt": attempt,
                               "job_id": job_ref}, str(exc))


def _handle_eval(payload: str, chat_fn) -> None:
    """Score one answered request with the local LLM-as-judge and persist it."""
    job = json.loads(payload)
    try:
        scores = score_payload(chat_fn, job)
        with SyncSessionLocal() as db:
            persist_eval(db, job, scores)
        record_eval(job.get("request_id"), scores.as_dict())  # -> Phoenix
        logger.info("eval stored for request %s", job.get("request_id"))
    except Exception as exc:  # noqa: BLE001 - eval failures must not kill the worker
        logger.warning("eval failed for %s: %s", job.get("request_id"), exc)


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    redis_client = sync_client()
    embedder = get_embedder()
    qindex = QdrantIndex()
    setup_tracing()
    _judge_chat_fn = None  # lazily built on first eval (avoids LLM client at boot)
    logger.info("worker starting, queues=[%s, %s]", _settings.ingest_queue, _settings.eval_queue)

    while _running:
        _touch_heartbeat()
        try:
            item = redis_client.blpop([_settings.ingest_queue, _settings.eval_queue],
                                      timeout=BLOCK_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - transient redis
            logger.warning("redis blpop failed: %s", exc)
            time.sleep(1)
            continue
        if item is None:
            continue
        queue, payload = item
        # Refresh liveness at job start too: a long parse/OCR job must not let
        # the heartbeat go stale mid-work (healthcheck window is generous, but
        # the idle-tick touch alone only covers time between jobs).
        _touch_heartbeat()
        try:
            if queue == _settings.ingest_queue:
                _handle_job(payload, redis_client, embedder, qindex)
            else:
                if _judge_chat_fn is None:
                    _judge_chat_fn = default_chat_fn()
                _handle_eval(payload, _judge_chat_fn)
        except Exception as exc:  # noqa: BLE001 - one bad payload must never kill the worker
            logger.exception("unhandled error for payload on %s: %s", queue, exc)

    logger.info("worker stopped cleanly")


if __name__ == "__main__":
    main()
