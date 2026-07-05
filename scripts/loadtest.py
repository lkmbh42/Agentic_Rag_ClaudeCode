"""Concurrency load test with pass/fail thresholds.

Simulates N concurrent users hammering an endpoint, reports p50/p95/p99 latency
and error rate, and exits non-zero if thresholds are breached (CI-gateable).

By default it targets POST /search (auth + ACL retrieval + Qdrant) — the path
that must scale to ~50 concurrent employees. Full generation load is a GPU-target
concern (see docs/production.md); on a CPU laptop point this at /search.

Usage (host, with the dev stack up):
    python scripts/loadtest.py --users 50 --requests-per-user 5 --p95-ms 1500
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time

import httpx


async def _login(base: str, email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{base}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


async def _collection_id(base: str, token: str) -> str | None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{base}/collections", headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        cols = r.json()
        return cols[0]["id"] if cols else None


# Mixed DE/EN query lengths for the /chat scenario (Phase 1 load test shape).
CHAT_QUERIES = [
    "Wie hoch ist das Tagegeld?",
    "Summarize the remote work security policy and list every rule that applies to laptops.",
    "Was regelt die IT-Richtlinie zu Passwörtern und wie oft müssen sie geändert werden?",
    "Who approves business trips?",
]

# Phase 5 "mixed" scenario: text sessions + visual (image-heavy) sessions run
# concurrently. Visual questions route to the ColQwen2 page path + VLM context,
# which is the heavier turn — the DoD sets a looser P95 for them (≤12s visual,
# ≤8s text). Tagged so the report breaks P95 out per modality.
TEXT_QUERIES = [(q, "text") for q in CHAT_QUERIES]
VISUAL_QUERIES = [
    ("Was zeigt das Balkendiagramm im Quartalsbericht?", "visual"),
    ("Describe the diagram on page 3 and read the axis values.", "visual"),
    ("Welche Werte zeigt das Umsatzdiagramm für 2024?", "visual"),
    ("What trend does the cost chart show over the last year?", "visual"),
]


async def _user_loop(client, base, token, endpoint, payloads, n, latencies, errors):
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(n):
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{base}{endpoint}", headers=headers,
                                  json=payloads[i % len(payloads)])
            latencies.append((time.perf_counter() - t0) * 1000)
            if r.status_code >= 400:
                errors.append(r.status_code)
        except Exception:  # noqa: BLE001
            errors.append(-1)


async def _mixed_user_loop(client, base, token, queries, n, by_modality, errors):
    """A user session that fires labeled (query, modality) turns at /chat and
    records latency per modality (Phase 5 mixed scenario)."""
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(n):
        query, modality = queries[i % len(queries)]
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{base}/chat", headers=headers, json={"message": query})
            by_modality[modality].append((time.perf_counter() - t0) * 1000)
            if r.status_code >= 400:
                errors.append(r.status_code)
        except Exception:  # noqa: BLE001
            errors.append(-1)


def _pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(p * (len(values) - 1))))], 1)


async def _run_mixed(args, token) -> int:
    """50 concurrent mixed text/visual chat sessions (CLAUDE.md Phase 5 task 1).
    Half the users run visual sessions, half text; P95 gated per modality."""
    by_modality: dict[str, list[float]] = {"text": [], "visual": []}
    errors: list[int] = []
    limits = httpx.Limits(max_connections=args.users + 10)
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=120, limits=limits) as client:
        tasks = []
        for u in range(args.users):
            queries = VISUAL_QUERIES if u % 2 else TEXT_QUERIES
            tasks.append(_mixed_user_loop(client, args.base, token, queries,
                                          args.requests_per_user, by_modality, errors))
        await asyncio.gather(*tasks)
    wall = time.perf_counter() - started

    total = args.users * args.requests_per_user
    error_rate = len(errors) / total if total else 1.0
    print(f"MIXED users={args.users} total={total} wall={wall:.1f}s "
          f"throughput={round(total / wall, 1) if wall else 0} req/s")
    ok = error_rate <= args.max_error_rate
    for mod, target in (("text", args.p95_text_ms), ("visual", args.p95_visual_ms)):
        lat = by_modality[mod]
        p50, p95, p99 = _pct(lat, 0.5), _pct(lat, 0.95), _pct(lat, 0.99)
        mod_ok = p95 <= target
        ok = ok and mod_ok
        print(f"  {mod:6} n={len(lat):4} p50={p50} p95={p95} p99={p99} "
              f"(target p95<={target}ms -> {'PASS' if mod_ok else 'FAIL'})")
    print(f"errors={len(errors)} error_rate={error_rate:.3%} -> "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", default="admin@example.com")
    ap.add_argument("--password", default="admin-pass-123")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--requests-per-user", type=int, default=5)
    ap.add_argument("--endpoint", default="/search")
    ap.add_argument("--query", default="security policy remote work")
    ap.add_argument("--p95-ms", type=float, default=1500.0)
    ap.add_argument("--max-error-rate", type=float, default=0.01)
    # Phase 5 mixed scenario: half the users run visual (image-heavy) sessions,
    # half text; P95 is gated per modality (visual ≤12s, text ≤8s).
    ap.add_argument("--scenario", choices=["endpoint", "mixed"], default="endpoint")
    ap.add_argument("--p95-text-ms", type=float, default=8000.0)
    ap.add_argument("--p95-visual-ms", type=float, default=12000.0)
    args = ap.parse_args()

    token = await _login(args.base, args.email, args.password)

    if args.scenario == "mixed":
        return await _run_mixed(args, token)
    # /chat takes {"message": ...} and cycles mixed-length DE/EN queries;
    # /search takes {"query": ...} with the single --query.
    if args.endpoint.startswith("/chat"):
        payloads = [{"message": q} for q in CHAT_QUERIES]
    else:
        payloads = [{"query": args.query}]
    if args.endpoint == "/search":
        coll = await _collection_id(args.base, token)
        if coll is None:
            print("FAIL: no accessible collection to search")
            return 2

    latencies: list[float] = []
    errors: list[int] = []
    limits = httpx.Limits(max_connections=args.users + 10)
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=60, limits=limits) as client:
        await asyncio.gather(*[
            _user_loop(client, args.base, token, args.endpoint, payloads,
                       args.requests_per_user, latencies, errors)
            for _ in range(args.users)
        ])
    wall = time.perf_counter() - started

    total = args.users * args.requests_per_user
    error_rate = len(errors) / total if total else 1.0
    p50, p95, p99 = _pct(latencies, 0.5), _pct(latencies, 0.95), _pct(latencies, 0.99)
    rps = round(total / wall, 1) if wall else 0.0

    print(f"users={args.users} total_requests={total} wall={wall:.1f}s throughput={rps} req/s")
    print(f"latency_ms p50={p50} p95={p95} p99={p99}")
    print(f"errors={len(errors)} error_rate={error_rate:.3%}")

    ok = p95 <= args.p95_ms and error_rate <= args.max_error_rate
    print(f"thresholds: p95<={args.p95_ms}ms error_rate<={args.max_error_rate:.1%} -> "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
