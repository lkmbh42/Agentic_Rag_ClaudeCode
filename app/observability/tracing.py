"""OpenTelemetry tracing exported to local Phoenix (air-gapped).

Only OBSERVABLE spans/attributes are emitted — request id, anonymized user,
router decision, retrieval latency + retrieved document ids + chunk types +
scores, generation latency, retry count, cache hit. We deliberately do NOT record
prompts, raw model reasoning, or chain-of-thought.
"""

from __future__ import annotations

import hashlib
import logging
import time

from app.config import get_settings

logger = logging.getLogger("rag.tracing")
_settings = get_settings()
_provider = None


def setup_tracing(exporter=None) -> None:
    """Idempotent. Pass `exporter` (e.g. InMemorySpanExporter) in tests."""
    global _provider
    if _provider is not None:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SimpleSpanProcessor,
        )

        provider = TracerProvider(resource=Resource.create({"service.name": "agentic-rag"}))
        if exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        elif _settings.tracing_enabled:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            endpoint = f"http://{_settings.phoenix_host}:{_settings.phoenix_grpc_port}"
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
        trace.set_tracer_provider(provider)
        _provider = provider
    except Exception as exc:  # noqa: BLE001 - tracing must never break requests
        logger.warning("tracing setup failed: %s", exc)


def _anon(user_id) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]


def record_request(result: dict, total_ms: float, request_id: str, user_id) -> None:
    """Emit a parent 'rag.request' span with child 'retrieve' / 'generate' spans."""
    try:
        from opentelemetry import trace
    except Exception:  # noqa: BLE001
        return

    tracer = trace.get_tracer("rag")
    chunks = result.get("chunks", [])
    now = time.time_ns()
    r_ms = float(result.get("retrieval_latency_ms", 0) or 0)
    g_ms = float(result.get("generation_latency_ms", 0) or 0)
    start = now - int(total_ms * 1e6)

    parent = tracer.start_span("rag.request", start_time=start)
    parent.set_attribute("request.id", request_id)
    parent.set_attribute("user.id", _anon(user_id))
    parent.set_attribute("router.decision", result.get("route") or "")
    parent.set_attribute("cache.hit", bool(result.get("cache_hit", False)))
    parent.set_attribute("retry.count",
                         int(result.get("retrieval_retries", 0)) + int(result.get("generation_retries", 0)))
    parent.set_attribute("end_to_end.latency_ms", round(total_ms, 1))
    parent.set_attribute("insufficient", bool(result.get("insufficient", False)))
    ctx = trace.set_span_in_context(parent)

    rspan = tracer.start_span("retrieve", context=ctx, start_time=start)
    rspan.set_attribute("retrieval.latency_ms", round(r_ms, 1))
    rspan.set_attribute("retrieval.num_chunks", len(chunks))
    rspan.set_attribute("retrieval.document_ids", [c["document_id"] for c in chunks])
    rspan.set_attribute("retrieval.chunk_types", [c.get("chunk_type", "") for c in chunks])
    rspan.set_attribute("retrieval.scores", [round(float(c.get("score", 0)), 4) for c in chunks])
    rspan.end(end_time=start + int(r_ms * 1e6))

    g_start = start + int(r_ms * 1e6)
    gspan = tracer.start_span("generate", context=ctx, start_time=g_start)
    gspan.set_attribute("generation.latency_ms", round(g_ms, 1))
    gspan.set_attribute("generation.num_citations", len(result.get("citations", [])))
    gspan.end(end_time=g_start + int(g_ms * 1e6))

    parent.end(end_time=now)


def record_eval(request_id, scores: dict) -> None:
    """Emit an 'eval' span carrying the judge scores (logged to Phoenix)."""
    try:
        from opentelemetry import trace
    except Exception:  # noqa: BLE001
        return
    tracer = trace.get_tracer("rag")
    span = tracer.start_span("eval")
    span.set_attribute("request.id", str(request_id))
    for key, val in scores.items():
        span.set_attribute(f"eval.{key}", val)
    span.end()


def flush() -> None:
    if _provider is not None:
        try:
            _provider.force_flush()
        except Exception:  # noqa: BLE001
            pass
