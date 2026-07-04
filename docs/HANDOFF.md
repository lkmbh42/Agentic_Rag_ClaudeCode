# HANDOFF — Multimodal RAG Migration (session continuation)

> Read this FIRST when resuming work. It is the durable state-of-the-world.
> `CLAUDE.md` (repo root) is the governing spec — its OPERATING RULES and phase
> gates are non-negotiable. This file records where we are inside that plan.

Last updated: 2026-07-04 (Phase 4 gate) · Branch: `feat/multimodal-migration` · HEAD at handoff: `cdc4922`

---

## 0. TL;DR — what to do first

1. `git log --oneline -15` and read `docs/CHANGELOG.md`.
2. Confirm clean tree on `feat/multimodal-migration`.
3. **Phase 3 APPROVED 2026-07-04.** **Phase 4 is CODE-COMPLETE and committed but
   NOT approved.** Present the Phase 4 gate (section 4 below) and STOP. Do
   **not** start Phase 5 until the operator writes exactly `PHASE 4 APPROVED`.
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
| 3 — Visual retrieval & fusion | ✅ DONE, **APPROVED** 2026-07-04 | operator wrote PHASE 3 APPROVED (decisions 1–4 + GPU deferrals ratified) |
| 4 — VLM answering & frontend | ✅ **CODE-COMPLETE, awaiting gate** | **needs PHASE 4 APPROVED** |
| 5 — Scale, security & cutover | ⏳ NEXT (do not start yet) | — |

---

## 3. What Phase 4 shipped (commits after the Phase 3 gate; Phase 3 map → CHANGELOG)

```
e7db980 docs: record PHASE 3 APPROVED gate (2026-07-04), Phase 4 started
f24fa23 multimodal generate + answer prompt contract (DE/EN)
6827149 ACL-checked media endpoints — gateway-proxied MinIO images
d215a2a message feedback — 👍/👎 + reason persisted per (message, user)
1b8287f frontend — citation chips with doc+Seite, ACL thumbnails, feedback UI
e4e25f4 config(phase4): answer-model serving — ADR 24GB default, documented VL overlay
```

New/changed modules (Phase 2–3 module maps live in docs/CHANGELOG.md):
- `app/llm/client.py` — `generate(..., images=[b64,...])` builds OpenAI content parts
  (data URLs) for VL serving; plain string without images. `llm_multimodal` (config)
  gates the whole image path; FALSE per ADR on 24 GB (visual answers come from
  pre-computed captions), the ≥48 GB VL overlay flips it (.env.example + PINS.md).
- `app/graph/prompts.py` — Phase 4 answer contract (DE/EN): context-only, no outside
  documents, [n] citations, read-vs-estimated chart qualifier, uninterpreted-figure
  honesty (ADR), refusal. CI-pinned by `tests/test_answer_contract.py`.
- `app/api/media.py` (NEW) — `/media/pages/{doc}/{page}`, `/media/figures/{doc}/{fig}`:
  JWT + collection ACL (404 semantics), gateway-proxied MinIO, never presigned.
- `app/models/chat.py::MessageFeedback` + migration `a81f5c9e3b02` —
  `POST /chat/messages/{id}/feedback` (up/down + reason, upsert per message+user,
  ownership-enforced); both chat endpoints return `message_id`; session detail carries
  the caller's rating.
- `app/graph/citations.py` — citations now carry `image_uri` (figure crops) so the UI
  can thumbnail them; retriever/graph propagate it.
- `admin-ui/app/src/` — CitationChip (`[n] file.pdf · Seite N` + toggleable AuthThumb
  through /media as blob URLs), FeedbackBar; `tsc --noEmit` clean.
- `docker-compose.yml` — `LLM_MULTIMODAL` env (default false), `LLM_GEN/CLASS_MODEL`
  overridable for the two-vLLM VL topology.

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

## 4. Phase 4 DoD — gate checklist (present this, then wait)

| DoD item | Status | Evidence |
|---|---|---|
| Visual correctness ≥70% (judge) | ⚠️ **GPU-deferred (flagged)** | requires real captions (VLM) or query-time VL — both GPU-host; dev visual answers come from stub captions. Mechanism (fusion → assembler → contract) fully wired + tested |
| Text ≥ baseline (judge) | ✅ **43.9% ≥ 42.1% baseline** (Phase 1: 45.4%, within documented judge noise); pass 68.0% = Phase 1; hit@5 75.0% | `eval/reports/phase4_text.md` (100 cases, judge on, 0 errors, 142 min dev CPU) |
| Citation accuracy ≥90% (sampled) | ⚠️ dev proxy: citation→correct-doc **72.8%** (↑ from 71.7%); citation-present 87% (↓ from 95% — dev-3B soft-refusals/prose citations, mechanism intact); the human-sampled ≥90% check runs on the GPU host with the prod model | `eval/reports/phase4_text.md` |
| Chart-value read-vs-estimated qualifier (prompt-contract test) | ✅ | `tests/test_answer_contract.py::test_contract_clauses_present_in_both_languages` (DE+EN clauses CI-pinned) |
| Image URLs unreachable without valid JWT + ACL (CI security test) | ✅ | `tests/test_media.py` — 401 unauth, cross-scope 404, probe 404, authorized 200 |
| Streaming stable under 20 concurrent streams | ⚠️ **GPU-deferred (flagged)** | SSE verified live with 3 concurrent streams on dev CPU (tokens + done + message_id, correct routes); 20-stream stability needs prod serving |

Decisions needing operator ratification at this gate:
1. **Active answer-model configuration.** CLAUDE.md says swap to Qwen2.5-VL-32B-AWQ;
   the ratified ADR VRAM budget (§0.5) shows it cannot fit the 24 GB host and §0.3
   mandates zero query-time VLM calls there. Shipped: ADR default active (text 7B-AWQ,
   `LLM_MULTIMODAL=false`, visual answers from pre-computed captions) + the VL-32B
   `.env` overlay documented for ≥48 GB (PINS.md Phase 4 table). Ratify or direct
   hardware growth.
2. **Citation protocol stays [n], UI renders "doc · Seite N".** The spec's literal
   `[doc, Seite N]` free-typed by the model would break the machine-verified
   anti-fabrication guard (extract_citations maps [n] → packed context). The UI chip
   shows exactly `file.pdf · Seite N` from verified metadata.
3. **GPU deferrals** (visual correctness ≥70%, 20-stream stability, text parity of
   whatever model serves prod) — same shape as every prior gate's deferrals.

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
     (full = 178 tests; `-m "not docling and not llm"` = 164 fast; marker `docling` =
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

## 6. Phase 5 preview (start ONLY after PHASE 4 APPROVED)

Per CLAUDE.md Phase 5 — scale, security & cutover:
1. Load test on prod hardware: 50 concurrent mixed sessions; P95 ≤12 s visual / ≤8 s
   text; 30-min soak, zero OOM; tune vLLM knobs and document values.
2. Rate limiting per user + global admission control (429 UI state).
3. Security pass: ACL red-team script across EVERY path — text, visual (docs_pages),
   cache (scope-hash), MinIO (/media), metadata lookup; `acl_audit.py` is reusable;
   pip-audit/npm audit; container hardening; audit log completeness.
4. Observability: Prometheus + Grafana dashboards committed, alert rules.
5. Backup/restore runbooks incl. Qdrant snapshots + MinIO; tested restore.
6. `docs/RUNBOOK.md`, bulk corpus ingest, 25-user pilot → GA.

GPU-host checklist accumulated across gates (run at provisioning, before pilot):
Phase 1 vLLM parity + 50-user load · Phase 2 caption quality ≥85% + real-corpus
volume run · Phase 3 visual hit@5 ≥75% (`run_eval.py --retrieval-only`) + router
p95 ≤400 ms (`router_report.py`) · Phase 4 text parity of the served model, visual
correctness ≥70%, 20-stream stability, sampled citation accuracy ≥90%.

Deferred observations still parked (AUDIT.md §11): chat per-turn state reset, SSE
circuit breaker, upload size cap. Baseline to beat lives in `eval/reports/baseline.md`.

---

## 7. Where the important context lives

- `CLAUDE.md` — governing spec, phase DoDs, model manifest.
- `docs/AUDIT.md` — Phase 0 audit: module map, ACL path + diagram, findings F1–F8, deferred obs.
- `docs/PINS.md` — image digests (applied), model HF-revision pins (open, operator provisioning).
- `docs/CHANGELOG.md` — per-phase summary incl. every Phase 2 decision + rollback notes.
- `eval/reports/baseline.md` — Phase 0 baseline; `phase1_text.md`, `phase1_load.md` — Phase 1.
- Memory (auto-loaded on this machine/project): `phase-status`, `dev-stack-quirks`.
