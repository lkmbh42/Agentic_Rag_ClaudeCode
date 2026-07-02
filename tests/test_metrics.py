"""Metrics DoD: /metrics/summary returns the live-ops contract with real values.
The endpoint is admin-only (operational internals must not be anonymous)."""

from __future__ import annotations


async def test_metrics_summary_requires_admin(client, seed, login):
    assert (await client.get("/metrics/summary")).status_code == 401
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    assert (await client.get("/metrics/summary", headers=alice)).status_code == 403


async def test_metrics_summary_shape_and_values(client, seed, login):
    from app.observability import metrics

    metrics.record_latency(120.0)
    metrics.record_latency(240.0)
    metrics.record_cache(True)
    metrics.record_cache(False)

    headers = await login(seed["admin"]["email"], seed["admin"]["password"])
    resp = await client.get("/metrics/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "queue_depth", "vllm_queue_wait_ms", "indexing_backlog",
        "cache_hit_rate", "latency_ms",
    }
    assert set(body["latency_ms"]) == {"p50", "p95", "p99"}
    assert 0.0 <= body["cache_hit_rate"] <= 1.0
    assert body["latency_ms"]["p95"] >= body["latency_ms"]["p50"]
    assert isinstance(body["indexing_backlog"], int)
