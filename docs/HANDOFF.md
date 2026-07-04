# HANDOFF — Multimodal RAG Migration (session continuation)

> Read this FIRST when resuming work. It is the durable state-of-the-world.
> `CLAUDE.md` (repo root) is the governing spec — its OPERATING RULES and phase
> gates are non-negotiable. This file records where we are inside that plan.

Last updated: 2026-07-04 (Phase 3 gate) · Branch: `feat/multimodal-migration` · HEAD at handoff: `51230f1`

---

## 0. TL;DR — what to do first

1. `git log --oneline -15` and read `docs/CHANGELOG.md`.
2. Confirm clean tree on `feat/multimodal-migration`.
3. **Phase 2 APPROVED 2026-07-04.** **Phase 3 is CODE-COMPLETE and committed but
   NOT approved.** Present the Phase 3 gate (section 4 below) and STOP. Do
   **not** start Phase 4 until the operator writes exactly `PHASE 3 APPROVED`.
4. Do not re-do finished work. Everything is committed; verify, don't rebuild.

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
| 3 — Visual retrieval & fusion | ✅ **CODE-COMPLETE, awaiting gate** | **needs PHASE 3 APPROVED** |
| 4 — VLM answering & frontend | ⏳ NEXT (do not start yet) | — |
| 5 — Scale, security & cutover | ⏳ | — |

---

## 3. What Phase 3 shipped (commits on the branch after the Phase 2 gate)

```
530000e docs: record PHASE 2 APPROVED gate (2026-07-04), Phase 3 started
68361d5 fix(deps): openai 1.54 -> 1.58 — 1.54 crashes against httpx 0.28
4594f37 fix(ops): alembic env keeps existing app loggers enabled
1d67393 config(phase3): visual/fusion/metadata/context/cache-purge tunables
44e7e5f query intent router — 4 intents, few-shot DE/EN, deterministic fallback
c670e44 visual retriever — ColQwen2 query embedding, docs_pages MAX_SIM, in-query ACL
2310b93 metadata path — ACL-scoped Postgres lookup (+ documents.uploaded_by_id)
85a4e7d context assembler — token/image budgets, ACL re-check, base64 at the edge
5b9ecf8 intent-routed graph — fusion, metadata node, page hits, /search pages
09161ab semantic cache — ACL-scope-hash key, expired-entry eviction
34c61d8 eval: visual_hit@5 metric + --retrieval-only mode
51230f1 eval: phase3 retrieval + router reports (dev run)
```

New/changed modules (Phase 2 module map lives in docs/CHANGELOG.md):
- `app/router/` (NEW) — `IntentRouter.classify()` → `text|visual|metadata|multi_doc`;
  few-shot DE/EN prompt in `app/graph/prompts.py::INTENT_ROUTER_SYSTEM`; validation +
  `text` fallback outside the model; rides `get_class_llm()` (Qwen2.5-3B role).
- `app/retrieval/visual.py` (NEW) — query → colqwen `/embed_query` → `docs_pages`
  MAX_SIM with in-query ACL filter, top-4; degrades to [] in dev.
- `app/retrieval/fusion.py` (NEW) — RRF (k=60) merge of reranked text + MAX_SIM pages;
  ties text-first; consumed by the assembler as packing order.
- `app/retrieval/metadata_lookup.py` (NEW) — deterministic ACL-scoped Postgres lookup
  for the metadata intent; DE/EN rendering; `documents.uploaded_by_id` (migration
  `f3a9c1d24e57`, backfilled from audit log) supplies the "author" facet.
- `app/context/` (NEW) — assembler: ACL re-check (CRITICAL log on drop), hard token
  budget, ≤4 images, s3://→base64 only here; `packed_chunks` = citation ground truth.
  Generator passes `max_images=0` until Phase 4's VLM consumes images.
- `app/graph/` — router node uses IntentRouter (prod runtime pins it to the class
  model); `metadata_lookup` node (hits→generator, miss→retriever); visual intent runs
  page retrieval alongside text; legacy 9-category routes + `unsupported` node removed;
  `route` in API/audit now carries the intent; citations carry `file_name`.
- `app/retrieval/semantic_cache.py` — scope-hash cache key (STRICT equality, in-query
  filter), opportunistic + periodic eviction (`purge_expired()`, worker sweep).
- `app/api/search.py` — `include_pages` flag returns visual-path results for the eval.

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

## 4. Phase 3 DoD — gate checklist (present this, then wait)

| DoD item | Status | Evidence |
|---|---|---|
| Router accuracy ≥90% on labeled set (CI test) | ✅ **94.4%** | `tests/test_router.py::test_router_accuracy_on_labeled_set` (marker `llm`, real model) — 68/72; all misses degrade to `text`; `eval/reports/phase3_router.md` |
| Text hit@5 ≥ baseline | ✅ **75.0% vs 73.9%** | `eval/reports/phase3_retrieval.md` (130-case retrieval-only run, live dev stack) |
| Visual hit@5 ≥75% | ⚠️ **GPU-deferred (flagged)** | mechanism proven end-to-end (docs_pages MAX_SIM + in-query ACL + `/search include_pages` + `visual_hit@5` metric); dev colqwen is the deterministic stub and `docs_pages` is empty under `VISUAL_PATH=degraded` |
| Cache never returns a hit across differing ACL scopes (explicit test) | ✅ | `tests/test_semantic_cache.py::test_scope_hash_is_the_cache_key` (+ `test_never_served_cross_scope`); scope-hash filtered inside the Qdrant query |
| Assembler enforces token + image budgets under adversarial test | ✅ | `tests/test_context_assembler.py` (200×500-token flood, 10-image flood, oversized-first-block, ACL re-check CRITICAL) |
| p95 added router latency ≤400 ms | ⚠️ **GPU-deferred (flagged)** | dev CPU p95 = 3481 ms (Ollama, ~350-token prefill); the CI test asserts ≤400 ms automatically once `LLM_BACKEND=vllm`; re-measure via `eval/router_report.py` |

Decisions needing operator ratification at this gate:
1. **4-intent taxonomy supersedes the legacy 9-category router.** The graph no longer
   consumes `ROUTES`; the `unsupported` dead-end class is removed (small models over-used
   it); `route` in API/audit responses now carries `text|visual|metadata|multi_doc`.
2. **Schema extension `documents.uploaded_by_id`** (nullable, FK users SET NULL,
   migration `f3a9c1d24e57`, backfilled from audit-log UPLOAD entries) — the spec's
   metadata "author" facet had no data source; ratify the KEEP-component touch.
3. **Cache scope-hash is STRICTER than the old subset rule** — differing permission
   sets never share entries (superset users included); hit rate pays for hard scope
   isolation; pre-Phase-3 entries are never served (cold-cache migration).
4. **GPU deferrals** (visual hit@5 ≥75%, router p95 ≤400 ms) — same shape as the
   Phase 1 load and Phase 2 caption-quality deferrals the operator already accepted.

Incidental fixes surfaced and committed separately:
- `68361d5`: openai 1.54 + httpx 0.28 = TypeError at client construction (Phase 2's
  "openai 1.54 is fine" was wrong; masked because graph tests inject FakeLLM).
- `4594f37`: in-process alembic (test harness) silenced all app loggers
  (`fileConfig(disable_existing_loggers=False)` now).
- Citations now propagate `file_name` (AUDIT §11 deferral folded in).

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
     (full = 163 tests; `-m "not docling and not llm"` = 149 fast; marker `docling` =
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

## 6. Phase 4 preview (start ONLY after PHASE 3 APPROVED)

Per CLAUDE.md Phase 4 — VLM answering & frontend:
1. Swap vLLM served model to Qwen2.5-VL-32B-Instruct-AWQ (pinned); text-only parity
   first (golden text subset ≥ Phase 1 score).
2. Answer prompt contract (DE/EN): cite `[doc, Seite N]`; "abgelesen" vs "geschätzt"
   qualifier for chart values; refuse on insufficient context.
3. Streaming end-to-end (SSE exists; extend to image-context turns).
4. Frontend: citation chips, inline thumbnails via gateway-proxied ACL-checked MinIO
   URLs (never presigned), 👍/👎 feedback to Postgres.
5. Full golden_v2 run → `eval/reports/phase4.md`.
Phase-3 hooks ready for it: the assembler already produces base64 images — flip the
generator's `max_images=0` to the config value and pass `assembled.images` into the
VLM call; page_hits are in graph state; `context_images` is tracked.

Deferred observations still parked (AUDIT.md §11): chat per-turn state reset, SSE
circuit breaker, upload size cap. GPU-host checklist additionally: visual hit@5 gate,
router p95 gate, Phase 1 vLLM parity + load, Phase 2 caption quality + volume run.
Baseline to beat lives in `eval/reports/baseline.md`.

---

## 7. Where the important context lives

- `CLAUDE.md` — governing spec, phase DoDs, model manifest.
- `docs/AUDIT.md` — Phase 0 audit: module map, ACL path + diagram, findings F1–F8, deferred obs.
- `docs/PINS.md` — image digests (applied), model HF-revision pins (open, operator provisioning).
- `docs/CHANGELOG.md` — per-phase summary incl. every Phase 2 decision + rollback notes.
- `eval/reports/baseline.md` — Phase 0 baseline; `phase1_text.md`, `phase1_load.md` — Phase 1.
- Memory (auto-loaded on this machine/project): `phase-status`, `dev-stack-quirks`.
