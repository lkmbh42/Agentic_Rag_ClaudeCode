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
from app.ingestion.indexer import index_document
from app.ingestion.qdrant_index import QdrantIndex
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
    try:
        with SyncSessionLocal() as db:
            count = index_document(db, uuid.UUID(document_id), embedder=embedder, qindex=qindex)
        logger.info("indexed %s (%d chunks, attempt %d)", document_id, count, attempt)
    except Exception as exc:  # noqa: BLE001
        if attempt + 1 < _settings.max_indexing_retries:
            logger.warning("index failed %s (attempt %d): %s — requeueing", document_id, attempt, exc)
            enqueue_index_sync(redis_client, document_id, attempt + 1)
        else:
            logger.error("index permanently failed %s after %d attempts: %s",
                         document_id, attempt + 1, exc)


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
        if queue == _settings.ingest_queue:
            _handle_job(payload, redis_client, embedder, qindex)
        else:
            if _judge_chat_fn is None:
                _judge_chat_fn = default_chat_fn()
            _handle_eval(payload, _judge_chat_fn)

    logger.info("worker stopped cleanly")


if __name__ == "__main__":
    main()
