# Production hardening guide

Covers load testing, GPU/VRAM tuning, deployment, backup/restore, failure
recovery, per-user quotas, and the security checklist. Pairs with the ADR
(`ADR.md`) and the dev/prod split (`docs/dev-vs-prod.md`).

---

## 1. Concurrency: per-user quotas (already enforced)

`app/core/ratelimit.py` enforces, per user, via Redis:
- **requests/minute** (`PER_USER_REQUESTS_PER_MIN`, default 60) → 429 when exceeded;
- **in-flight concurrency** (`PER_USER_MAX_INFLIGHT`, default 3) → 429 when exceeded;
  the slot is released on request completion (with a 300s safety expiry).

Circuit breakers (Phase 5) bound a single request's work; quotas stop one user
from flooding the queue. Both are required.

---

## 2. Load test (50 concurrent users)

Harness: `scripts/loadtest.py` (async httpx; reports p50/p95/p99 + error rate;
exits non-zero if thresholds breached — CI-gateable).

```bash
# from the compose network (so the hostname resolves)
docker compose -f docker-compose.dev.yml run --rm --no-deps \
  -v "$(pwd -W 2>/dev/null || pwd):/srv" backend \
  python scripts/loadtest.py --base http://backend:8000 \
    --users 50 --requests-per-user 5 --p95-ms 1500 --max-error-rate 0.01
```

**Pass/fail thresholds**

| Path | Target | Rationale |
|---|---|---|
| `/search` (ACL retrieval) | p95 ≤ 1500 ms, errors ≤ 1% @ 50 users | The path every request shares; must scale. **Verified on the laptop: p95 ≈ 1340 ms, 0 errors, ~63 req/s.** |
| `/chat` (full generation) | p95 ≤ 8 s @ 50 users **on the prod GPU** | CPU/3B dev model cannot meet this — generation latency is a GPU concern. Run this target against the prod vLLM (7B-AWQ) deployment, not the laptop. |

The dev laptop validates the API/retrieval/cache/auth tier at 50 users. Generation
latency is validated on the GPU server (§3).

---

## 3. GPU / VRAM tuning (prod, 24 GB target — see ADR 0.5)

Budget (single 24 GB GPU): `vllm` ~17 GB + `embeddings` ~4 GB ≈ 21 GB; VLM is CPU.

Tune in `.env`, then `docker compose up -d vllm`:

| Symptom | Knob | Direction |
|---|---|---|
| CUDA OOM at load | `VLLM_GPU_MEMORY_UTILIZATION` | lower (e.g. 0.72 → 0.65) |
| OOM under concurrency | `VLLM_MAX_NUM_SEQS` | lower (48 → 32) |
| Long-context OOM | `VLLM_MAX_MODEL_LEN` | lower (8192 → 4096) |
| Headroom to spare | `VLLM_MAX_NUM_SEQS` | raise for throughput |
| Router/grader latency | `VLLM_SCHEDULING_POLICY=priority` | keep (short calls jump queue) |

On 48 GB+, move to the two-vLLM topology (separate fast-classification model),
upgrade generation to 14B-AWQ/FP16, and make the VLM GPU-resident.

vLLM container needs `ipc: host` + `shm_size` (set in `docker-compose.yml`) or it
crashes under load.

---

## 4. Server deployment

1. Install Docker + the **NVIDIA Container Toolkit**.
2. Pre-stage model weights into `${MODELS_DIR}` (air-gapped — no runtime download):
   `qwen2.5-7b-instruct-awq/`, `bge-m3/`, `bge-reranker-v2-m3/`, the VLM.
3. `cp .env.example .env`; set strong `JWT_SECRET`, `POSTGRES_PASSWORD`,
   `LLM_BASE_URL=http://vllm:8000/v1`, `EMBEDDINGS_BACKEND=service`.
4. `docker compose up -d --build` (builds the BGE-M3 image via `INSTALL_MODELS=true`).
5. `docker compose exec backend alembic upgrade head`.
6. Reach the app through the `proxy` service (add TLS — terminate at the proxy or
   a fronting LB). Run behind the reverse proxy only; do not expose service ports.

---

## 5. Backup & restore (consistent Postgres + Qdrant)

Scripts: `scripts/backup.sh` (pg_dump `--clean` + Qdrant snapshots) and
`scripts/restore.sh` (psql restore + Qdrant snapshot recover). `restore.sh` stops
the app tier so the restored state is mutually consistent.

```bash
bash scripts/backup.sh ./backups/$(date +%F)     # both stores, point-in-time pair
bash scripts/restore.sh ./backups/2026-06-22      # app tier auto-stopped/started
```

**Verified restore drill:** a document's `(Postgres chunks, Qdrant points)` went
`1/1` → `0/0` (delete) → `1/1` (restore) — both stores recovered in agreement.

Also back up the **`documents_data` volume** (original uploaded files) if you need
to re-index after restore: `docker run --rm -v agentic-rag_documents_data:/d -v
$PWD/backups:/b alpine tar czf /b/docs.tgz -C /d .`. The LangGraph checkpointer
tables live in Postgres and are included in the pg_dump.

Schedule `backup.sh` via cron; keep N days offsite/offline.

---

## 6. Failure recovery

| Failure | Behavior | Recovery |
|---|---|---|
| vLLM/Ollama down | LLM calls degrade to safe defaults (router→simple_rag, generate→insufficient); circuit breakers bound retries | restart `vllm`; requests recover automatically |
| Qdrant down | retrieval returns empty → "insufficient evidence" (no crash) | restart `qdrant`; restore from snapshot if data lost |
| Redis down | denylist check fails open (short-lived tokens bound exposure); metrics/quotas degrade | restart `redis` |
| Postgres down | requests 5xx; backend retries via `pool_pre_ping` | restart `postgres`; restore from dump if data lost |
| One bad PDF | indexing job retries to `MAX_INDEXING_RETRIES`, then `FAILED` status; never blocks others | fix/re-upload; `POST /documents/{id}/reindex` |
| Request too slow | `MAX_REQUEST_DURATION_S` returns 504 | tune model/concurrency |
| Worker crash | heartbeat healthcheck restarts it; jobs remain queued in Redis | automatic |

---

## 7. Security checklist (pre-go-live)

- [ ] `JWT_SECRET` is a long random secret; `POSTGRES_PASSWORD` changed from default.
- [ ] Seed/admin default credentials rotated; no default creds in prod.
- [ ] TLS terminated at the proxy; only the proxy port is exposed publicly.
- [ ] Service ports (Postgres/Redis/Qdrant/Phoenix/vLLM) NOT published to the host in prod.
- [ ] Air-gapped at runtime verified: no egress; models mounted, not fetched.
- [ ] RBAC + ACL enforced at retrieval, cache, and generation (tested).
- [ ] Semantic cache never served cross-scope (tested); invalidation on delete/ACL-change wired.
- [ ] Per-user quotas + circuit breakers enabled.
- [ ] Audit logging on login/upload/generation/admin actions.
- [ ] Containers run as non-root (`appuser`).
- [ ] Backups scheduled and a restore drill rehearsed.
- [ ] Phoenix traces contain no chain-of-thought / prompts (verified).
- [ ] Refresh-token rotation + Redis jti denylist active; admin suspend revokes sessions.
