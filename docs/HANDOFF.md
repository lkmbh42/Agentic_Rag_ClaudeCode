# HANDOFF — Multimodal RAG Migration (session continuation)

> Read this FIRST when resuming work. It is the durable state-of-the-world.
> `CLAUDE.md` (repo root) is the governing spec — its OPERATING RULES and phase
> gates are non-negotiable. This file records where we are inside that plan.

Last updated: 2026-07-04 · Branch: `feat/multimodal-migration` · HEAD at handoff: `10a0a63`

---

## 0. TL;DR — what to do first

1. `git log --oneline -15` and read `docs/CHANGELOG.md`.
2. Confirm clean tree on `feat/multimodal-migration`.
3. **Phase 2 is code-complete and committed but NOT approved.** Present the Phase 2
   gate (section 4 below) and STOP. Do **not** start Phase 3 until the operator
   writes exactly `PHASE 2 APPROVED`.
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
| 2 — Multimodal ingestion pipeline | ✅ **CODE-COMPLETE, awaiting gate** | **needs PHASE 2 APPROVED** |
| 3 — Visual retrieval & fusion | ⏳ NEXT (do not start yet) | — |
| 4 — VLM answering & frontend | ⏳ | — |
| 5 — Scale, security & cutover | ⏳ | — |

---

## 3. What Phase 2 shipped (11 commits, all on the branch)

```
f98adce MinIO object store — pinned image, SSE-on, typed client, tests
75b1524 semantic chunker — token windows, heading bounds, table fidelity
5a7d367 ingest_jobs progress tracking + worker DLQ/resume (extends BLPOP worker)
c8a2b47 fix(repo): track app/models/* — silently gitignored since init
e2839da Docling layout-aware parser (PDF/DOCX/PPTX/XLSX, de+en OCR)
1c515ac fix: worker survives stale queue payloads (DocumentGone) + loop guard
f1b7f8f figure pipeline — crop to MinIO, VLM /caption, type=figure chunks
c36f436 page-image pipeline — render, ColQwen2 service, docs_pages multivector
0a79a39 idempotency + ACL-payload gates, ACL auditor, sampling harness
370c01e admin UI ingestion status, re-ingest, failure reason
10a0a63 refresh service lockfiles (vlm, colqwen stub images)
```

New/changed modules:
- `app/ingestion/object_store.py` — MinIO client (`figures/{doc_id}/{figure_id}.png`,
  `pages/{doc_id}/{page_no}.png`); internal `s3://` URIs only, no presigned/public URLs.
- `app/ingestion/chunker.py` — `build_chunks_v2`: 350–600-token windows, 15% overlap,
  heading-bounded; tables → GitHub-MD + one-line summary + row-serialization (>8 rows).
- `app/ingestion/docling_parser.py` — Docling parse → typed blocks (text|table|figure)
  with page geometry; tesseract `deu+eng` OCR. Legacy parsers kept as `PARSER_BACKEND=legacy`.
- `app/ingestion/figures.py` — `FigureCaptioner` → `vlm` service `POST /caption`; graceful
  fallback to document caption; never raises.
- `app/ingestion/pages.py` + `pages_index.py` — render ≤1024px (PyMuPDF) → MinIO → ColQwen2
  multivector → Qdrant `docs_pages` (MAX_SIM, binary quantization, ACL payload).
- `app/ingestion/jobs.py` + `app/models/ingest.py` + migration `d91a4b7f02e1` — `ingest_jobs`
  table (QUEUED/PARSING/CAPTIONING/INDEXING/INDEXED/FAILED), retries reuse the row,
  dead-letter list `ingest:dlq`, `requeue_dlq()`.
- `app/ingestion/acl_audit.py` — scans a Qdrant collection for objects missing ACL payload
  (reused by Phase 5 red-team).
- `worker/main.py` — job progress via `on_stage`, DLQ, resilient to stale payloads.
- `services/vlm/main.py` — `POST /caption` (Qwen2.5-VL-7B); deterministic `[STUB-Caption]`
  in dev, real model when `VLM_IMPLEMENTED=true`.
- `services/colqwen/` (NEW) + `docker/colqwen.Dockerfile` — `/embed_image` + `/embed_query`;
  deterministic stub in dev, real `vidore/colqwen2-v1.0` (colpali-engine) when
  `COLQWEN_IMPLEMENTED=true`.
- `app/api/documents.py` — `GET /documents/{id}/ingest-status` (ACL-scoped).
- `admin-ui/app/src/{api.ts,App.tsx,styles.css}` — Documents view shows stage/attempt/
  re-ingest/failure-reason. `tsc --noEmit` clean.
- Compose: `minio` (prod+dev, pinned digest, SSE-S3 auto-encryption on), `colqwen` (prod GPU),
  worker mounts `/models` + `DOCLING_ARTIFACTS_PATH`. All image digests pinned (docs/PINS.md).

Key dependency facts (do not "fix"):
- `docling==2.108.0` EXACT — the `2.15.*` range resolved an incompatible `docling-core` that
  broke imports; the pair must move together.
- `httpx` bumped `0.27.*` → `0.28.*` because docling 2.108 requires >=0.28 (openai 1.54 is fine).
- `libgl1` + `libglib2.0-0` added to `docker/backend.Dockerfile` for TableFormer's opencv.
- `tesseract-ocr-deu` + `tesseract-ocr-eng` language packs added (fixes AUDIT §8 EN-only OCR gap).

---

## 4. Phase 2 DoD — gate checklist (present this, then wait)

| DoD item | Status | Evidence |
|---|---|---|
| 3 real docs of each type ingest end-to-end | ⚠️ partial (flagged) | fixture corpus of every type parses in tests + live PDF ingest verified; "real-corpus 3-of-each" volume run is a GPU-host step (no real corpus in repo — AUDIT §8) |
| Table fidelity ≥90% (manual review) | ✅ tooling / ⚠️ human sign-off | `eval/ingest_sample.py` side-by-side HTML; tables extracted structured, never flattened (`tests/test_chunker.py`, `test_docling_parser.py`) |
| Caption QA ≥85% useful | ⚠️ GPU-deferred (flagged) | crop→MinIO→/caption→chunk mechanism proven; dev uses `[STUB-Caption]`; real quality on GPU host |
| Re-ingest → zero new vectors (CI) | ✅ | `tests/test_ingest_gates.py::test_reingest_creates_zero_new_vectors` |
| ACL payload on 100% of new objects (automated) | ✅ | `app/ingestion/acl_audit.py` + `test_all_indexed_objects_carry_acl_payload`; live chunk confirmed |
| docs_pages storage measured; binary quantization confirmed | ✅ | live: MAX_SIM + BinaryQuantization(always_ram) active; ~32× (400KB→12.5KB / 50 pages) |

Three decisions needing operator ratification at this gate:
1. **Extended the BLPOP worker** (added `ingest_jobs`/DLQ/progress) instead of rewriting to
   arq/rq — brownfield rule; justified in `docs/CHANGELOG.md` Phase 2.
2. **Captioning reuses the `vlm` service boundary** (`POST /caption`), superseding the 501
   stub (CLAUDE.md §10), not a parallel endpoint.
3. **GPU deferrals** (caption quality, ColQwen2 retrieval quality, real-corpus volume run):
   dev proves wiring with deterministic stubs + `VISUAL_PATH=degraded`; quality gates run at
   GPU provisioning — same deferral shape the operator already accepted in Phase 1 (load test).

Incidental fixes surfaced and committed separately:
- `c8a2b47`: `app/models/*` was silently gitignored since init (`models/` pattern caught
  `app/models/`); a clean checkout couldn't boot. Pattern root-anchored, files committed.
- `1c515ac`: worker survives stale queue payloads for deleted docs instead of crashing on FK.

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
     (full = 126 tests; `-m "not docling"` skips the slow layout-model tests, ~10 of them).
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

## 6. Phase 3 preview (start ONLY after PHASE 2 APPROVED)

Per CLAUDE.md Phase 3 — query-time use of the new collections:
1. Query router (`app/router/`, Qwen2.5-3B) → `text | visual | metadata | multi_doc`; JSON-only,
   deterministic `text` fallback; unit tests ≥90% on a labeled set of ≥60 queries.
2. Metadata path → Postgres-filtered lookup first.
3. Fusion: text-hybrid + ColQwen2 retrieval per intent; RRF merge; text through bge-reranker;
   visual top-4 by MAX_SIM.
4. Context assembler (`app/context/`): hard token budget, citations, ACL re-verification before
   assembly (defense in depth), image URIs → base64 only here.
5. Semantic cache upgrade: cache key includes user's ACL-scope hash (never leak across scopes) —
   this also closes AUDIT finding F1/F4. Also fold in the deferred expired-entry eviction noted
   in AUDIT §11.
6. Retrieval eval: visual hit@5 ≥75%, text hit@5 ≥ baseline; p95 added router latency ≤400ms.

Deferred observations parked for Phase 3+ (AUDIT.md §11): ACL-scoped cache keys (F1), chat
per-turn state reset, SSE circuit breaker, upload size cap, citations `file_name` propagation.
Baseline to beat lives in `eval/reports/baseline.md`.

---

## 7. Where the important context lives

- `CLAUDE.md` — governing spec, phase DoDs, model manifest.
- `docs/AUDIT.md` — Phase 0 audit: module map, ACL path + diagram, findings F1–F8, deferred obs.
- `docs/PINS.md` — image digests (applied), model HF-revision pins (open, operator provisioning).
- `docs/CHANGELOG.md` — per-phase summary incl. every Phase 2 decision + rollback notes.
- `eval/reports/baseline.md` — Phase 0 baseline; `phase1_text.md`, `phase1_load.md` — Phase 1.
- Memory (auto-loaded on this machine/project): `phase-status`, `dev-stack-quirks`.
