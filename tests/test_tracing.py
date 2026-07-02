"""Tracing DoD: a request produces a trace with the required spans and NO
chain-of-thought (no prompts / raw model reasoning in span attributes)."""

from __future__ import annotations

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability import tracing


def test_request_trace_has_required_spans_without_cot():
    exporter = InMemorySpanExporter()
    tracing._provider = None  # reset module guard for the test
    tracing.setup_tracing(exporter=exporter)

    result = {
        "route": "simple_rag", "cache_hit": False,
        "retrieval_retries": 1, "generation_retries": 0,
        "retrieval_latency_ms": 5.0, "generation_latency_ms": 12.0,
        "chunks": [{"document_id": "d1", "chunk_type": "text", "score": 0.91}],
        "citations": [{"marker": 1}], "insufficient": False,
    }
    tracing.record_request(result, total_ms=40.0, request_id="req-1", user_id="user-1")
    tracing.flush()

    spans = exporter.get_finished_spans()
    names = {s.name for s in spans}
    assert {"rag.request", "retrieve", "generate"} <= names

    parent = next(s for s in spans if s.name == "rag.request")
    attrs = dict(parent.attributes)
    assert attrs["router.decision"] == "simple_rag"
    assert attrs["request.id"] == "req-1"
    assert attrs["retry.count"] == 1
    # user id is anonymized (hashed), not the raw value
    assert attrs["user.id"] != "user-1"

    retrieve = next(s for s in spans if s.name == "retrieve")
    rattrs = dict(retrieve.attributes)
    assert rattrs["retrieval.document_ids"] == ("d1",)
    assert rattrs["retrieval.chunk_types"] == ("text",)

    # No chain-of-thought: no span carries prompts / answers / messages.
    forbidden = {"prompt", "answer", "messages", "content", "completion", "context"}
    for span in spans:
        for key in dict(span.attributes):
            assert not any(f in key.lower() for f in forbidden), f"CoT leak: {key}"
