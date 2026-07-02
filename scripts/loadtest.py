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


async def _user_loop(client, base, token, endpoint, payload, n, latencies, errors):
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{base}{endpoint}", headers=headers, json=payload)
            latencies.append((time.perf_counter() - t0) * 1000)
            if r.status_code >= 400:
                errors.append(r.status_code)
        except Exception:  # noqa: BLE001
            errors.append(-1)


def _pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(p * (len(values) - 1))))], 1)


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
    args = ap.parse_args()

    token = await _login(args.base, args.email, args.password)
    payload = {"query": args.query}
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
            _user_loop(client, args.base, token, args.endpoint, payload,
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
