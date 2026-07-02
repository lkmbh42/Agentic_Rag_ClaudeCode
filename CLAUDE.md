# CLAUDE.md — Multimodal RAG Platform Migration (Brownfield)

## PROJECT IDENTITY

**Project:** Migration of existing air-gapped Agentic RAG platform (text-only, ~50 users, Ollama) to a **multimodal RAG platform** (text + tables + charts + diagrams + photos, 500 users, vLLM).

**Type:** BROWNFIELD MIGRATION. This is NOT a rewrite. The existing codebase is the foundation. You extend and replace components surgically. Any proposal to rewrite a working module must be justified in writing and approved by the operator before implementation.

**Existing stack (KEEP):** FastAPI gateway (JWT auth, RBAC), React SPA, PostgreSQL (users, ACLs, doc metadata, audit log), Qdrant (text collection, hybrid dense+sparse), Redis (semantic cache, sessions), reranker service.

**To REPLACE:** Ollama serving → vLLM. Text-only answer LLM → Qwen2.5-VL-32B-Instruct (AWQ).

**To BUILD NEW:** Multimodal ingestion pipeline (Docling + VLM captioning + ColQwen2 page embeddings), MinIO object store, visual retrieval collection + RRF fusion, query router.

---

## OPERATING RULES (NON-NEGOTIABLE)

1. **Phase gates:** Do not begin a phase until the previous phase's Definition of Done (DoD) is fully met and the operator has explicitly written "PHASE N APPROVED".
2. **Air-gap discipline:** No runtime code may call external APIs. All models are local files with **pinned revisions** (exact HF commit hash or local path). Any model reference without a pinned revision is a build failure. Model downloads happen ONLY in the documented, operator-executed provisioning step — never at container start.
3. **No silent scope creep:** If a task requires touching a KEEP component beyond its stated extension, stop and report before editing.
4. **Idempotent everything:** Ingestion jobs, migrations, and provisioning scripts must be safely re-runnable. Re-ingesting the same document version must not create duplicate chunks (dedupe on `doc_id + content_hash`).
5. **ACL invariant:** Every retrievable object (text chunk, table chunk, figure caption, page-image vector, MinIO object) carries the same permission payload schema. A retrieval path that can return an object without an ACL filter applied is a CRITICAL bug — halt and report.
6. **Tests before gate:** Each phase ends with automated tests committed to the repo. "It worked when I ran it" does not satisfy a DoD.
7. **Config over code:** All tunables (chunk sizes, top-k, image budget, model paths) live in a single typed settings module (`pydantic-settings`), overridable via env.
8. **Language:** Corpus and users are German-dominant with English/mixed documents. All prompts, eval sets, and OCR configs must handle `de` + `en`.

---

## TARGET ARCHITECTURE

```
                         ┌──────────────────────────────┐
React SPA ── HTTPS ──►   │ FastAPI Gateway              │
(citations, image        │ JWT · RBAC · rate limit      │
 previews in answers)    └──────────┬───────────────────┘
                                    │
                         ┌──────────▼───────────────────┐
                         │ Query Router (Qwen2.5-3B)    │
                         │ intents: text | visual |     │
                         │ metadata | multi-doc-summary │
                         └───┬──────────┬───────────────┘
                             │          │
              ┌──────────────▼──┐   ┌───▼──────────────────┐
              │ Hybrid text     │   │ Visual retrieval     │
              │ retrieval       │   │ ColQwen2 multivector │
              │ BGE-M3 + BM25   │   │ (Qdrant, MAX_SIM,    │
              │ → bge-reranker  │   │  binary quantized)   │
              └──────────────┬──┘   └───┬──────────────────┘
                             │  RRF     │
                         ┌───▼──────────▼───────────────┐
                         │ Context Assembler            │
                         │ token budget · ≤4 page imgs  │
                         │ ACL re-check · citations     │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │ vLLM: Qwen2.5-VL-32B AWQ     │
                         │ (OpenAI-compatible endpoint) │
                         └──────────────────────────────┘

INGESTION (offline batch, queue-driven via Redis):
 upload → Docling (layout + TableFormer) → text/table/figure split
   text  → semantic chunk → BGE-M3 → Qdrant `docs_text`
   table → Markdown chunk + row serialization → Qdrant `docs_text` (type=table)
   figure→ crop → MinIO  +  Qwen2.5-VL-7B caption → Qdrant `docs_text` (type=figure)
 full pages → render PNG (≤1024px) → MinIO + ColQwen2 → Qdrant `docs_pages`

STORAGE: PostgreSQL (metadata/ACL/audit) · Qdrant (2 collections) · MinIO (images) · Redis (cache/queue)
```

---

## MODEL MANIFEST (PIN BEFORE PHASE 1)

| Role | Model | Serving | Pin |
|---|---|---|---|
| Answer VLM | `Qwen/Qwen2.5-VL-32B-Instruct-AWQ` | vLLM, tensor-parallel | `<HF_REVISION_HASH>` |
| Ingest captioner | `Qwen/Qwen2.5-VL-7B-Instruct` | vLLM batch (off-peak) | `<HF_REVISION_HASH>` |
| Router | `Qwen/Qwen2.5-3B-Instruct` | vLLM (same server, second model or CPU-offload variant) | `<HF_REVISION_HASH>` |
| Embeddings | `BAAI/bge-m3` | TEI or ONNX service | `<HF_REVISION_HASH>` |
| Reranker | `BAAI/bge-reranker-v2-m3` | TEI | `<HF_REVISION_HASH>` |
| Visual retriever | `vidore/colqwen2-v1.0` | custom service (colpali-engine) | `<HF_REVISION_HASH>` |

Operator fills `<HF_REVISION_HASH>` during provisioning. CI fails if any placeholder remains.

---

## PHASE 0 — AUDIT & BASELINE

**Goal:** Full understanding of the existing codebase; frozen baseline to measure regressions against.

**Tasks:**
1. Produce `docs/AUDIT.md`: module map of the existing repo — every service, its entrypoints, DB schemas, Qdrant collection schema, env vars, Docker services, and inter-service contracts.
2. Verify and document the current ACL enforcement path end-to-end (upload → payload → retrieval filter). Include a sequence diagram in the audit doc.
3. Pin ALL current dependencies (`pip freeze`/lockfiles, Docker image digests). Commit lockfiles.
4. Verify `OLLAMA_LLM_MODEL` (or successor env) points to the local model only; grep the repo for any cloud endpoint references and list them in the audit.
5. Build/refresh the **golden eval set v2**: 100 text questions (reuse existing) + 30 NEW visual questions (charts, tables, diagrams, scanned pages) with ground-truth answers and source page references. Store as `eval/golden_v2.jsonl`.
6. Implement `eval/run_eval.py`: automated scoring (answer correctness via LLM-judge rubric + citation accuracy + retrieval hit@k). Run against the CURRENT system; commit the baseline report `eval/reports/baseline.md`.

**DoD Phase 0:**
- [ ] `docs/AUDIT.md` complete, reviewed by operator
- [ ] ACL sequence diagram present; no unfiltered retrieval path found (or all findings listed with severity)
- [ ] All dependencies pinned; zero cloud endpoints in runtime code (or exceptions documented)
- [ ] `golden_v2.jsonl` with 130 QA pairs committed
- [ ] Baseline eval report committed (visual questions expected to fail — that is the point)

---

## PHASE 1 — SERVING MIGRATION: OLLAMA → vLLM (TEXT PARITY)

**Goal:** Swap serving infra with zero functional change. Same text model class, same answers, better concurrency.

**Tasks:**
1. Add `vllm` service to `docker-compose.yml` (official `vllm/vllm-openai` image, pinned digest). Serve the current text model (or Qwen2.5-32B-Instruct-AWQ as interim) with pinned revision, `--max-model-len` sized to current context usage.
2. Introduce `LLM_BACKEND` setting; refactor all LLM call sites to a single client module (`app/llm/client.py`) using the OpenAI-compatible API (base URL from config). Remove Ollama-specific code paths behind a feature flag, then delete after parity is proven.
3. Health checks, startup ordering, and graceful-degradation behavior (gateway returns 503 with clear message if LLM backend is down).
4. Load test: `locust` or `k6` scenario, 50 concurrent chat users, mixed query lengths. Record P50/P95/P99 latency and tokens/sec into `eval/reports/phase1_load.md`.
5. Re-run golden eval (text subset). Delta vs baseline must be neutral-or-better.

**DoD Phase 1:**
- [ ] All LLM traffic flows through vLLM; Ollama container removed from compose
- [ ] Single typed LLM client module; no scattered HTTP calls
- [ ] Text eval score ≥ baseline (within judge noise, documented)
- [ ] Load report: P95 < 8s at 50 concurrent (tune or flag hardware constraint)
- [ ] Rollback documented: one-line compose change restores previous backend

---

## PHASE 2 — MULTIMODAL INGESTION PIPELINE (NEW BUILD)

**Goal:** Replace the text-only extractor with a layout-aware, multimodal pipeline. This phase has the highest quality leverage — do not rush the gate.

**Tasks:**
1. **MinIO** service in compose (pinned digest), bucket layout: `figures/{doc_id}/{figure_id}.png`, `pages/{doc_id}/{page_no}.png`. Server-side encryption on; access only via internal network.
2. **Docling integration** (`ingest/parser.py`): PDF/DOCX/PPTX/XLSX + scanned PDFs (OCR fallback with German+English). Output: ordered blocks typed as `text | table | figure | caption` with page geometry.
3. **Chunking** (`ingest/chunker.py`): semantic chunking for text (target 350–600 tokens, overlap 15%, respect heading boundaries). Tables: (a) full table as GitHub-Markdown chunk prefixed with an auto-generated one-line summary, (b) row-serialized chunks (`"Zeile: Spalte1=…, Spalte2=…"`) when table >8 rows. Never flatten tables to whitespace text.
4. **Figure pipeline** (`ingest/figures.py`): crop figure regions → PNG to MinIO → batch-caption via Qwen2.5-VL-7B with a fixed German/English prompt that extracts: description, axis/legend values, visible text (OCR), and stated trends. Caption becomes a `type=figure` chunk with `image_uri` payload.
5. **Page rendering** (`ingest/pages.py`): render each page ≤1024px longest edge → MinIO → ColQwen2 multivector → Qdrant `docs_pages` collection (multivector config, `MAX_SIM`, **binary quantization enabled**, ACL payload identical to text schema).
6. **Queue-driven workers:** Redis-backed job queue (e.g. `arq` or `rq`), idempotent per `doc_id + content_hash`, resumable, dead-letter list, progress persisted to Postgres (`ingest_jobs` table). Nightly batch schedule for GPU-heavy captioning.
7. **Admin UI extension:** ingestion status per document (queued/parsing/captioning/indexed/failed), re-ingest button, failure reason display.
8. **Quality sampling harness** (`eval/ingest_sample.py`): random 30-page sample report — side-by-side page image vs extracted text/tables/captions, output as HTML for manual review.

**DoD Phase 2:**
- [ ] 3 real corpus documents of each type (clean PDF, scanned PDF, DOCX, PPTX, table-heavy XLSX/PDF) ingest end-to-end without manual intervention
- [ ] Table fidelity: ≥90% of sampled tables structurally correct (headers, merged cells) in manual review of sampling report
- [ ] Caption QA: ≥85% of sampled figure captions rated "useful for retrieval" in review report
- [ ] Re-running ingestion on an unchanged document creates zero new vectors (idempotency test in CI)
- [ ] ACL payload present and schema-validated on 100% of new objects (automated check)
- [ ] `docs_pages` storage measured; binary quantization confirmed active

---

## PHASE 3 — VISUAL RETRIEVAL & FUSION

**Goal:** Query-time use of the new collections. Router + RRF fusion + reranking.

**Tasks:**
1. **Query router** (`app/router/`): Qwen2.5-3B classification into `text | visual | metadata | multi_doc`. Few-shot prompt, German+English examples, JSON-only output with schema validation and deterministic fallback (`text`) on parse failure. Unit tests with a labeled set of ≥60 routed queries, accuracy ≥90%.
2. **Metadata path:** `metadata` intent → Postgres-filtered lookup first (newest version, author, date), then optional retrieval.
3. **Fusion:** run text-hybrid and ColQwen2 retrieval per routed intent; RRF merge; text candidates through bge-reranker; visual hits ranked by MAX_SIM score, capped at top 4 pages.
4. **Context assembler** (`app/context/`): hard token budget (config), citation metadata (`doc_id`, page, chunk/figure id), ACL re-verification against the requesting user before assembly (defense in depth), image URIs resolved to base64 only at this stage.
5. **Semantic cache upgrade:** cache key includes user's ACL scope hash (a cached answer must never leak across permission boundaries). Similarity threshold configurable; hit/miss metrics exported.
6. Retrieval eval: hit@5 on golden_v2 retrieval targets — text ≥ baseline, visual questions hit@5 ≥ 75%.

**DoD Phase 3:**
- [ ] Router accuracy ≥90% on labeled set (CI test)
- [ ] Visual hit@5 ≥75%; text hit@5 ≥ baseline
- [ ] Cache never returns a hit across differing ACL scopes (explicit test)
- [ ] Assembler enforces token + image budgets under adversarial long-context test
- [ ] p95 added router latency ≤ 400ms

---

## PHASE 4 — VLM ANSWERING & FRONTEND

**Goal:** Qwen2.5-VL-32B answers over mixed text+image context; UI renders citations and image evidence.

**Tasks:**
1. Swap vLLM served model to Qwen2.5-VL-32B-Instruct-AWQ (pinned). Validate text-only parity first (golden text subset ≥ Phase 1 score).
2. **Answer prompt contract:** system prompt (DE/EN) enforcing: cite every claim `[doc, Seite N]`; distinguish "aus Achsenbeschriftung abgelesen" vs "visuell geschätzt" for chart values; refuse when context insufficient; never reference documents outside provided context.
3. Streaming responses end-to-end (SSE through gateway to React).
4. **Frontend:** citation chips linking to source; inline thumbnail of cited figures/pages (served via gateway-proxied, ACL-checked MinIO URLs — never presigned public URLs); feedback buttons (👍/👎 + reason) persisted to Postgres for eval mining.
5. Full golden_v2 eval run. Report `eval/reports/phase4.md`.

**DoD Phase 4:**
- [ ] Visual question correctness ≥70% on golden_v2 (judge-scored), text ≥ baseline
- [ ] Citation accuracy ≥90% (cited page actually supports claim, sampled)
- [ ] Chart-value answers carry the read-vs-estimated qualifier (prompt-contract test)
- [ ] Image URLs unreachable without valid JWT + ACL (security test in CI)
- [ ] Streaming stable under 20 concurrent streams

---

## PHASE 5 — SCALE, SECURITY & CUTOVER

**Goal:** Production readiness for 500 employees.

**Tasks:**
1. Load test: 50 concurrent mixed text/visual sessions (visual = image-heavy context). Targets: P95 ≤ 12s visual, ≤ 8s text; zero OOM over 30-min soak. Tune vLLM (`--gpu-memory-utilization`, `--max-num-seqs`, KV cache) and document final values.
2. Rate limiting per user + global admission control (queue depth cap with friendly 429 UI state).
3. **Security pass:** ACL red-team script attempting cross-tenant retrieval via every path (text, visual, cache, MinIO, metadata); dependency audit (`pip-audit`, `npm audit`); container hardening (non-root, read-only FS where possible); audit log covers query, retrieved doc ids, and answer hash.
4. Observability: Prometheus metrics (latency, tokens/s, cache hit rate, queue depth, GPU util via DCGM), Grafana dashboard JSON committed, alert rules for backend-down and P95 breach.
5. Backup/restore runbooks: Postgres, Qdrant snapshots, MinIO — tested restore, documented RTO.
6. Ops runbook `docs/RUNBOOK.md`: start/stop, model update procedure (with pin change + eval gate), re-ingestion, common failures.
7. Bulk-ingest full corpus (batched, nightly), monitor sampling reports.
8. Pilot rollout: 25 users, 1 week, feedback mined; then general availability.

**DoD Phase 5:**
- [ ] Load targets met on production hardware; tuning values documented
- [ ] Red-team script finds zero ACL bypasses; report committed
- [ ] Dashboards + alerts live; restore test performed and logged
- [ ] Full corpus ingested; failure rate <2% with all failures triaged
- [ ] Pilot feedback reviewed; go/no-go decision recorded
- [ ] Operator writes "MIGRATION ACCEPTED"

---

## GLOBAL DEFINITION OF DONE (applies to every phase)

- [ ] All new/changed code typed (Python: full type hints, mypy clean; TS: strict)
- [ ] Unit + integration tests added and passing in CI
- [ ] No secrets in code; all config via settings module
- [ ] `docker compose up` from clean checkout + provisioned model dir reaches healthy state
- [ ] `docs/CHANGELOG.md` updated with phase summary
- [ ] No placeholder `<HF_REVISION_HASH>` or `TODO(security)` remaining in touched files
