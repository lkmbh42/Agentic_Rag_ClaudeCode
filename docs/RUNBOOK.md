# Operations Runbook — Multimodal RAG Platform

Operator reference for the production stack (`docker-compose.yml`, single ~24 GB
GPU host, air-gapped at runtime). Dev differences are in
[dev-vs-prod.md](dev-vs-prod.md); architecture rationale in [../ADR.md](../ADR.md).

---

## 1. Start / stop

```bash
# Start everything (weights must already be staged under $MODELS_DIR — §5).
docker compose up -d

# Health: every service reports healthy; the gateway answers /healthz.
docker compose ps
curl -fsS http://localhost/api/health/ready | jq

# Graceful stop (keeps volumes) / full teardown (KEEPS named volumes).
docker compose stop
docker compose down            # add -v ONLY to wipe data volumes (destructive)
```

Startup ordering is handled by healthchecks: `backend`/`worker` wait for
postgres, redis, qdrant, vllm, embeddings. vLLM's `start_period` is 300 s
(weight load + CUDA graph capture); the gateway returns `503` with a clear
message until the LLM backend is reachable.

---

## 2. Model update procedure (pinned + eval-gated)

Models are pre-staged files with pinned HF revisions (Rule 2). Never update a
model in place without the eval gate.

1. Stage the new weights under `$MODELS_DIR` on the host (offline transfer).
2. Record the new HF revision hash in [PINS.md](PINS.md) (the manifest's
   `<HF_REVISION_HASH>` must not remain a placeholder).
3. Point the serving env at the new path (`VLLM_MODEL_PATH`,
   `VLLM_SERVED_MODEL_NAME`, and `LLM_GEN_MODEL`/`LLM_CLASS_MODEL`) in `.env`.
4. Recreate only the serving tier: `docker compose up -d vllm backend worker`.
5. **Eval gate (mandatory before go-live):** run the golden text subset and
   confirm ≥ the Phase 1 score before announcing the change:
   ```bash
   python eval/run_eval.py --subset text --report model_update_$(date +%F)
   ```
   For a VL model also run the visual subset (`--subset visual`) and the
   router accuracy check (`eval/router_report.py`).
6. Roll back by reverting the `.env` paths and `docker compose up -d vllm
   backend worker` — no code change (both models speak the OpenAI API).

Answer-model configurations (24 GB text default vs ≥48 GB VL overlay) are in
[PINS.md](PINS.md) "Phase 4 answer-model configurations".

---

## 3. Re-ingestion

Ingestion is idempotent (dedupe on `doc_id + content_hash`); re-ingesting an
unchanged document creates zero new vectors.

```bash
# Single document (admin UI: Documents → re-ingest, or API):
curl -fsS -XPOST http://localhost/api/documents/<doc_id>/reindex \
  -H "Authorization: Bearer <admin_jwt>"

# Bulk / nightly corpus load is queue-driven; watch progress:
curl -fsS http://localhost/api/metrics/summary -H "Authorization: Bearer <admin_jwt>" | jq
#   -> indexing_backlog + queue_depth
```

Failed jobs dead-letter to the Redis list `ingest:dlq`; requeue with the admin
helper (`app.ingestion.jobs.requeue_dlq`). Ingestion stage per document is
visible in the admin UI (queued/parsing/captioning/indexing/indexed/failed).

---

## 4. Backup & restore (tested)

`scripts/backup.sh` captures a mutually-consistent set of ALL THREE stores —
PostgreSQL (`pg_dump`), Qdrant (snapshots), MinIO (object mirror). Run during
low write activity.

```bash
COMPOSE="docker compose" bash scripts/backup.sh /srv/backups/$(date +%F)
# -> postgres.sql, qdrant_<collection>.snapshot, minio.tar

# Restore stops the app tier for a consistent window, then restarts it:
COMPOSE="docker compose" bash scripts/restore.sh /srv/backups/<date>
```

**RTO:** dominated by Qdrant snapshot re-index + MinIO mirror; on the reference
corpus a full restore completes in minutes. **Verify a restore quarterly** into
a scratch stack and confirm `/metrics/summary` + a smoke query.

---

## 5. Provisioning (first run, air-gapped)

1. Stage every model under `$MODELS_DIR` (offline): vLLM answer model, BGE-M3 +
   reranker, ColQwen2, VLM captioner, Docling layout models. Pins in
   [PINS.md](PINS.md).
2. Fill `.env` from `.env.example` — real secrets (`JWT_SECRET`,
   `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `MINIO_KMS_SECRET_KEY`,
   `GRAFANA_ADMIN_PASSWORD`). Never commit secrets.
3. `docker compose up -d`; run migrations: `docker compose exec backend python
   -m alembic upgrade head`; seed the first admin.
4. Bulk-ingest the corpus (nightly batch); monitor the sampling reports
   (`eval/ingest_sample.py`) and the indexing-backlog metric.

---

## 6. Common failures

| Symptom | Likely cause | Action |
|---|---|---|
| `/chat` returns 503 | vLLM unreachable (loading, crashed, OOM) | `docker compose logs vllm`; wait out `start_period`; check GPU memory; lower `VLLM_GPU_MEMORY_UTILIZATION`/`VLLM_MAX_NUM_SEQS` |
| `/chat` returns 429 | admission control saturated | expected under load; scale replicas or raise `GLOBAL_MAX_INFLIGHT` (watch `rag_global_inflight`) |
| Answers lack visual detail | visual path degraded / captioner down | check `vlm` health; `VISUAL_PATH=full`, `VLM_IMPLEMENTED=true` on the GPU host |
| Indexing backlog climbing | CPU captioning behind (ADR: monitored) | expected for large batches; throttle uploads or add worker replicas; alert fires >500 for 15m |
| Citation thumbnail 404 | MinIO object missing / not restored | verify `minio.tar` in the last backup; re-ingest the document |
| Migrations fail on boot | schema drift / partial upgrade | `alembic current` vs `heads`; restore from backup if inconsistent |
| Prometheus target down | backend/vllm unreachable | `BackendDown`/`VLLMDown` alerts; check the service and network |

---

## 7. Security operations

- **ACL red-team:** `python scripts/redteam_acl.py` provisions two tenants and
  probes every retrieval path for cross-tenant leakage; must report zero
  bypasses (latest: `eval/reports/phase5_redteam.md`). Re-run after any change
  to retrieval, cache, or the media endpoints.
- **Dependency audit:** `pip-audit -r requirements.txt` (backend) and
  `npm audit` (admin-ui) — findings + accepted exceptions logged in the Phase 5
  changelog entry.
- **Forced logout / suspend:** admin `revoke-sessions` takes effect immediately
  (Redis `jti` denylist); access tokens are 15 min.
- **Audit trail:** every generation logs query, retrieved document ids, and an
  answer hash (`audit_logs`, action `GENERATION`).
- **Secrets:** all via `.env`; MinIO is internal-network-only (images are only
  ever served through the ACL-checked gateway `/media` endpoints, never
  presigned).
