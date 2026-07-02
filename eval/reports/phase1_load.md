# Phase 1 load report — dev host (CPU) with GPU-host measurement flagged

- Date: 2026-07-02 · Git commit: `1e5e9ed` · Stack: `docker-compose.dev.yml` (all healthy)
- Serving: Ollama `qwen2.5:3b` on CPU (`LLM_BACKEND=ollama`) — **not** the Phase 1 target
  topology. The DoD target (P95 < 8 s chat at 50 concurrent) is defined against vLLM on the
  production 24 GB GPU; this host has no GPU (`nvidia-smi` absent). Per the Phase 1 DoD escape
  hatch this report **flags the hardware constraint** and records what the dev host can measure,
  plus the exact procedure to produce the definitive numbers during GPU provisioning.
- Harness: `scripts/loadtest.py` (async httpx, p50/p95/p99 + error-rate thresholds,
  CI-gateable). The spec names locust/k6; the committed harness predates Phase 1, measures the
  same quantities, and adds no dependency — documented equivalence, no new tooling introduced.

## 1. Retrieval path under 50 concurrent users — `POST /search` (CPU-meaningful)

`python scripts/loadtest.py --users 50 --requests-per-user 5 --p95-ms 1500`

| metric | value |
|---|---|
| total requests | 250 (50 users × 5) |
| throughput | 40.8 req/s |
| p50 / p95 / p99 | 832 ms / 2 656 ms / 2 847 ms |
| errors | 0 (0.000 %) |

Auth + ACL + hybrid Qdrant retrieval + rerank sustains 50 concurrent users with zero errors on
a laptop CPU. The 1.5 s p95 threshold fails (2.66 s) — acceptable dev-host result; the
retrieval path is not the Phase 1 bottleneck and gets re-measured on prod hardware in Phase 5.

## 2. Generation path — `POST /chat` (CPU characterization only)

Single-stream (sequential, mixed DE/EN lengths):

| request | latency | note |
|---|---|---|
| cold #1 | 169.9 s | 352-char answer |
| cache hit | 0.17 s | semantic cache |
| cold #2 | 121.7 s | 230-char answer |
| cold #3 | 63.8 s | 433-char answer |

Concurrency probe at the per-user in-flight cap (3 concurrent): slowest request exceeded the
300 s client timeout — the CPU host saturates below 3 concurrent generations. Admission
control behaves as designed (`per_user_max_inflight=3`, dev `MAX_REQUEST_DURATION_S=600`).

**Conclusion:** 50-concurrent chat load on this host is not a meaningful measurement — CPU
generation is 60–170 s/request single-stream. Cache hits (0.17 s) and retrieval (§1) are healthy.

## 3. Definitive measurement — GPU provisioning runbook step

On the prod GPU host after vLLM starts (pinned image `vllm/vllm-openai@sha256:251eba5…`,
`qwen2.5-7b-awq`, `--max-num-seqs 48`):

```
python scripts/loadtest.py --users 50 --requests-per-user 5 \
    --endpoint /chat --p95-ms 8000            # DoD: P95 < 8 s at 50 concurrent
```

(One authenticated user per simulated user is required — the per-user in-flight cap of 3
otherwise throttles the test client; seed 50 test users or raise the cap for the test window.
`scripts/loadtest.py` now sends the correct `{"message": ...}` payload for `/chat` and cycles
mixed-length DE/EN queries — extended in Phase 1 so this step is directly executable.)

Record tokens/s from vLLM `/metrics` during the run; append results to this report.
