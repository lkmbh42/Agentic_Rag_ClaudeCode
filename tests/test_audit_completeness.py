"""Phase 5 §3: the GENERATION audit entry must cover the query, the retrieved
document ids, and an answer hash. The detail builder is pure — tested directly."""

from __future__ import annotations

import hashlib
import uuid

from app.api.chat import _generation_audit_detail


def _state():
    d1, d2 = str(uuid.uuid4()), str(uuid.uuid4())
    return {
        "query": "Wie lang müssen Passwörter sein?",
        "answer": "Mindestens 14 Zeichen. [1]",
        "route": "text",
        "cache_hit": False,
        "insufficient": False,
        "chunks": [
            {"document_id": d1, "content": "…"},
            {"document_id": d2, "content": "…"},
            {"document_id": d1, "content": "…"},  # duplicate -> collapsed
        ],
    }, d1, d2


def test_detail_covers_query_docids_and_answer_hash():
    state, d1, d2 = _state()
    detail = _generation_audit_detail(state, "req-123")

    assert detail["query"] == state["query"]
    assert detail["retrieved_document_ids"] == sorted({d1, d2})
    assert detail["answer_sha256"] == hashlib.sha256(
        state["answer"].encode("utf-8")).hexdigest()
    # The raw answer is hashed, never stored in the audit detail.
    assert state["answer"] not in str(detail)
    assert detail["request_id"] == "req-123"
    assert detail["route"] == "text"
    assert detail["streamed"] is False


def test_streamed_flag_and_empty_state_are_safe():
    detail = _generation_audit_detail({}, "req-x", streamed=True)
    assert detail["streamed"] is True
    assert detail["retrieved_document_ids"] == []
    assert detail["query"] == ""
    # sha256 of the empty string — stable, never a crash on a missing answer.
    assert detail["answer_sha256"] == hashlib.sha256(b"").hexdigest()
