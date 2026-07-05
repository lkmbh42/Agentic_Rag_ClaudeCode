# HANDOFF — Multimodal RAG Migration (session continuation)

> Read this FIRST when resuming work. It is the durable state-of-the-world.
> `CLAUDE.md` (repo root) is the governing spec — its OPERATING RULES and phase
> gates are non-negotiable. This file records where we are inside that plan.

Last updated: 2026-07-05 (Phase 5 gate) · Branch: `feat/multimodal-migration` · HEAD at handoff: `4e44771`

---

## 0. TL;DR — what to do first

1. `git log --oneline -15` and read `docs/CHANGELOG.md`.
2. Confirm clean tree on `feat/multimodal-migration`.
3. **Phase 4 APPROVED 2026-07-05.** **Phase 5 is CODE-COMPLETE and committed but
   NOT approved.** Present the Phase 5 gate (section 4 below) and STOP. Phase 5
   is the LAST phase — its gate is the operator writing **`MIGRATION ACCEPTED`**
   after the pilot go/no-go. Do not declare the migration accepted yourself.
4. Do not re-do finished work. Everything is committed; verify, don't rebuild.
   ⚠️ NEVER `rm` a bind-mounted path from inside a container: dev compose mounts
   `./app` and `./worker` at `/srv/app` `/srv/worker`, so `rm -rf /srv/app`
   deletes the HOST source. Only remove copied assets (`/srv/tests`, `/srv/eval`).

---

## 1. Project identity (see CLAUDE.md for full detail)

Brownfield migration of an air-gapped text-only Agentic RAG platform (FastAPI +
React + Postgres + Qdrant + Redis + reranker, Ollama) into a **multimodal** RAG
platform (text + tables + charts + diagrams + photos, 500 users, vLLM,
Docling + VLM captioning + ColQwen2 page embeddings + MinIO + query router).
It is NOT a rewrite — extend/replace surgically; rewriting a working module needs
written justification + operator approval.

Non-negotiable rules that keep biting if forgotten:
- **Phase gates:** never start phase N+1 before operator writes "PHASE N APPROVED".
- **Air-gap:** no external API calls at runtime; models are local, pinned by HF
  revision; downloads happen only in the documented operator provisioning step.
- **ACL invariant (Rule 5):** every retrievable object (text/table/figure chunk,
  page vector, MinIO object) carries the same permission payload
  (`collection_id` + `document_id`). A retrieval path that can return an object
  without an ACL filter is a CRITICAL bug — halt and report.
- **Idempotency:** re-ingest of an unchanged doc must create zero new vectors.
- **Config over code:** all tunables in `app/config.py` (pydantic-settings), env-overridable.
- **Tests before gate:** each phase ends with committed automated tests.
- **Language (Rule 8):** corpus is German-dominant + English/mixed; prompts, OCR, evals must handle `de`+`en`.

---

## 2. Phase status

| Phase | State | Gate |
|---|---|---|
| 0 — Audit & baseline | ✅ DONE, **APPROVED** 2026-07-02 | operator wrote PHASE 0 APPROVED |
| 1 — Ollama→vLLM serving (text parity) | ✅ DONE, **APPROVED** 2026-07-03 | dev-Ollama hardware exception accepted |
| 2 — Multimodal ingestion pipeline | ✅ DONE, **APPROVED** 2026-07-04 | operator wrote PHASE 2 APPROVED (decisions 1–3 + GPU deferrals ratified) |
| 3 — Visual retrieval & fusion | ✅ DONE, **APPROVED** 2026-07-04 | operator wrote PHASE 3 APPROVED (decisions 1–4 + GPU deferrals ratified) |
| 4 — VLM answering & frontend | ✅ DONE, **APPROVED** 2026-07-05 | operator wrote PHASE 4 APPROVED (ADR-default serving + [n] protocol + GPU deferrals ratified) |
| 5 — Scale, security & cutover | ✅ **CODE-COMPLETE, awaiting gate** | **needs "MIGRATION ACCEPTED"** (after pilot go/no-go) |

---

## 3. What Phase 5 shipped (commits after the Phase 4 gate; earlier maps → CHANGELOG)

```
b60ea70 docs: record PHASE 4 APPROVED gate (2026-07-05), Phase 5 started
752c59e admission control, audit completeness, Prometheus/Grafana observability
ff23c51 MinIO backup/restore, RUNBOOK, mixed load scenario, container hardening
4e44771 ACL red-team (zero bypasses) + dependency audit findings + pillow bump
```

New/changed modules (Phase 2–4 module maps live in docs/CHANGELOG.md):
- `scripts/redteam_acl.py` (NEW) — provisions two tenants, probes every retrieval path
  (text/visual/cache/media/metadata + direct-object) for cross-tenant leakage; exits
  non-zero on any bypass. Report: `eval/reports/phase5_redteam.md` (9/9 denied).
- `app/core/ratelimit.py` — `acquire/release_global_slot` + `rate_limit` now enforce a
  global in-flight cap (friendly 429 + Retry-After); per-user quotas unchanged.
- `app/api/chat.py::_generation_audit_detail` — GENERATION audit carries query,
  retrieved doc ids, `answer_sha256` (both endpoints).
- `app/observability/metrics.py` + `app/main.py` — real Prometheus objects (latency
  Histogram, cache Counter, live gauges via `refresh_gauges` at scrape).
- `ops/` (NEW) — `prometheus/prometheus.yml`, `prometheus/alerts.yml`,
  `grafana/dashboard.json`. Prod compose gains pinned prometheus + grafana + an
  `x-hardening` anchor (`no-new-privileges` on all 13 services; all already non-root).
- `scripts/backup.sh` + `restore.sh` — now include MinIO (figures+pages) via `mc mirror`.
- `scripts/loadtest.py` — `--scenario mixed` (50 concurrent text+visual, per-modality P95).
- `docs/RUNBOOK.md` (NEW), `eval/reports/phase5_security.md` (NEW — audit triage).

Key dependency facts (do not "fix"):
- `docling==2.108.0` EXACT — the `2.15.*` range resolved an incompatible `docling-core` that
  broke imports; the pair must move together.
- `httpx==0.28.*` (docling needs >=0.28) **requires `openai>=1.55.3`** — 1.54 passes the
  removed `proxies=` kwarg and crashes at client construction (pinned `1.58.*`,
  fixed in Phase 3; FakeLLM-based tests will NOT catch a regression here).
- `libgl1` + `libglib2.0-0` in `docker/backend.Dockerfile` for TableFormer's opencv;
  tesseract `deu+eng` packs installed.
- alembic env.py must keep `disable_existing_loggers=False` — in-process migrations
  (the test harness) otherwise silence all `rag.*` loggers.

---

## 4. Phase 5 DoD — gate checklist (present this, then wait)

| DoD item | Status | Evidence |
|---|---|---|
| Load targets met on prod hardware; tuning documented | ⚠️ **GPU-deferred (flagged)** | `loadtest.py --scenario mixed` (50 concurrent text+visual, per-modality P95 gates ≤8s/≤12s) ready; the run + 30-min soak + vLLM tuning is a GPU-host step, like the Phase 1 load deferral |
| Red-team finds zero ACL bypasses; report committed | ✅ **0 bypasses / 9 probes** | `scripts/redteam_acl.py` live run — `eval/reports/phase5_redteam.md` (text, visual, cache, media, metadata, direct-object) |
| Dashboards + alerts live; restore test performed | ✅ artifacts / ⚠️ live-on-prod | `ops/` Prometheus scrape+alerts + Grafana dashboard committed; `/metrics` serves rag_* series (tested); prometheus+grafana in prod compose. Restore path scripted (Postgres+Qdrant+MinIO); **quarterly restore drill is a prod-host runbook step** |
| Full corpus ingested; failure rate <2%, all triaged | ⚠️ **GPU/corpus-deferred** | bulk nightly ingest + sampling-report review is a prod-host provisioning step (no real corpus in the repo — AUDIT §8) |
| Pilot feedback reviewed; go/no-go recorded | ⏳ **operator step** | feedback capture is live (`message_feedback` + eval mining); the 25-user 1-week pilot + go/no-go is the operator's |
| Operator writes "MIGRATION ACCEPTED" | ⏳ | the terminal gate — after the pilot go/no-go |

Additional security DoD (spec §3), all met on the dev stack:
- **Rate limiting + admission control:** per-user quotas (existing) + global in-flight cap
  with friendly 429 (`tests/test_ratelimit.py`).
- **Audit completeness:** query + retrieved doc ids + answer hash on every GENERATION
  (`tests/test_audit_completeness.py`).
- **Dependency audit:** npm clean; pip-audit 26 CVEs triaged with a remediation plan
  (`eval/reports/phase5_security.md`); pillow bumped.
- **Container hardening:** non-root (already) + `no-new-privileges` on all 13 services.

Decisions needing operator ratification at this gate:
1. **Dependency-remediation posture.** pip-audit found 26 CVEs (pillow, starlette,
   langgraph*). The low-risk pillow bump was applied; the starlette + langgraph fixes
   are major-version jumps that would destabilize the gated system on the eve of
   cutover, so they are recorded with a post-pilot patch-cycle plan
   (`eval/reports/phase5_security.md`) rather than bumped now. Ratify the plan, or
   direct an immediate coordinated bump + full re-gate.
2. **GPU/prod-host deferrals** (50-user mixed load + soak + vLLM tuning, full-corpus
   bulk ingest, quarterly restore drill, dashboards-live) — the accumulated
   provisioning checklist below. Same deferral shape accepted at every prior gate.
3. **Pilot go/no-go is yours.** Everything the pilot needs is in place (feedback loop,
   observability, admission control, ACL-clean). The 25-user week and the
   `MIGRATION ACCEPTED` decision are operator actions, not mine to declare.

### GPU-host / provisioning checklist (accumulated across all phases — run before GA)
- Phase 1: vLLM text parity + 50-user load (P95 < 8s).
- Phase 2: caption quality ≥85% + real-corpus 3-of-each volume run.
- Phase 3: visual hit@5 ≥75% (`run_eval.py --retrieval-only`) + router p95 ≤400 ms (`router_report.py`).
- Phase 4: served-model text parity ≥ Phase 1, visual correctness ≥70%, 20-stream stability, sampled citation ≥90%.
- Phase 5: 50-user mixed load + 30-min soak + vLLM tuning; full-corpus bulk ingest (<2% failures); quarterly restore drill; fill all `<HF_REVISION_HASH>` pins.

---

## 5. Dev environment — how to run things (CPU-only Windows host, Docker Desktop)

- Stack: `docker compose -f docker-compose.dev.yml up -d`. Dev keeps **Ollama** (CPU) not vLLM,
  and **no GPU** (`nvidia-smi` absent) — approved Phase 1 hardware exception.
- Admin creds: `admin@example.com` / `admin-pass-123`. Backend on :8000, MinIO :9000/:9001,
  Qdrant :6333, Ollama :11434.
- **pytest is NOT on the host or in the runtime image.** Run tests INSIDE the backend container:
  1. `docker compose -f docker-compose.dev.yml exec -T backend pip install "pytest==8.*" "pytest-asyncio==0.24.*" "reportlab==4.*"`
  2. copy assets in (only `./app`, `./worker` are bind-mounted): `for f in tests services eval pytest.ini scripts alembic alembic.ini; do docker compose -f docker-compose.dev.yml cp $f backend:/srv/$f; done`
     — if `/srv/tests` already exists, `cp` NESTS it; remove first as root: `exec -T -u root backend sh -c "rm -rf /srv/tests"`.
  3. `docker compose -f docker-compose.dev.yml exec -T backend python -m pytest -q`
     (full = 183 tests; `-m "not docling and not llm"` = 169 fast; marker `docling` =
     13 slow layout tests; marker `llm` = the router accuracy gate, 72 real LLM calls,
     ~4 min on the dev CPU).
- After changing `requirements*.txt` or the Dockerfile: rebuild (`docker compose -f
  docker-compose.dev.yml build backend worker`), recreate (`up -d backend worker`), then
  regenerate the lockfile from the pristine image:
  `docker run --rm agentic-rag-dev-backend pip freeze > requirements.lock`.
- Applying a new migration to dev DB: copy alembic in, `exec -T backend sh -c "cd /srv && python -m alembic upgrade head"`.
- Evals: `python eval/run_eval.py ...` runs from the HOST (httpx available). Full 130-case run
  ≈ 2h15m on this CPU. Known quirk: `run_eval.py` crashes on a Windows cp1252 print of "→"
  AFTER writing its report files — the reports are valid; the "failure" is cosmetic.
- Git Bash prints harmless `nvm: command not found` noise on every command — ignore it.
- Frontend typecheck without host node: `MSYS_NO_PATHCONV=1 docker run --rm -v "<abs>/admin-ui/app":/app -w /app node:20-alpine sh -c "npm ci && npx tsc --noEmit"`.

---

## 6. After PHASE 5 → the terminal gate

Phase 5 is the LAST build phase. There is no Phase 6: the migration is complete
when the operator writes **`MIGRATION ACCEPTED`** after the 25-user pilot go/no-go.
Everything the pilot needs is in place (feedback loop, observability, admission
control, ACL-clean red-team). Remaining work before GA is the operator's
provisioning + pilot, tracked by the GPU-host checklist in section 4.

If asked to "deploy on the server", the dev→prod switch is memory
[[agentic-rag-server-deploy-trigger]]: 24 GB-GPU config (vLLM + BGE-M3, re-index,
revert dev downgrades), then walk the section-4 GPU-host checklist.

Deferred observations still parked (AUDIT.md §11): chat per-turn state reset, SSE
circuit breaker, upload size cap (the last is also the interim mitigation for the
starlette CVEs — see `eval/reports/phase5_security.md`). Baseline: `eval/reports/baseline.md`.

---

## 7. Where the important context lives

- `CLAUDE.md` — governing spec, phase DoDs, model manifest.
- `docs/AUDIT.md` — Phase 0 audit: module map, ACL path + diagram, findings F1–F8, deferred obs.
- `docs/PINS.md` — image digests (applied), model HF-revision pins (open, operator provisioning).
- `docs/CHANGELOG.md` — per-phase summary incl. every Phase 2 decision + rollback notes.
- `eval/reports/baseline.md` — Phase 0 baseline; `phase1_text.md`, `phase1_load.md` — Phase 1.
- Memory (auto-loaded on this machine/project): `phase-status`, `dev-stack-quirks`.
