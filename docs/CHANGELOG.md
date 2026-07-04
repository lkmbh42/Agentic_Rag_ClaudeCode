# CHANGELOG — Multimodal RAG Migration

## Phase 3 — Visual retrieval & fusion (gate: "PHASE 3 APPROVED", 2026-07-04)

> Gate ratified all four flagged decisions: (1) 4-intent taxonomy supersedes the
> legacy router, (2) `documents.uploaded_by_id` schema extension, (3) strict
> scope-hash cache keying, (4) GPU deferrals (visual hit@5, router p95).

**Measured (dev host):** router accuracy **94.4%** on 72 labeled DE/EN queries
(DoD ≥90% ✅; all 4 misses degrade to the safe `text` path;
`eval/reports/phase3_router.md`); text hit@5 **75.0%** ≥ baseline 73.9% ✅
(`eval/reports/phase3_retrieval.md`); cross-scope cache test ✅; assembler
budget tests ✅. Full suite: 149 fast + 13 docling + 1 llm gate, all green.
**GPU-deferred (flagged):** visual hit@5 ≥75% (dev colqwen is the deterministic
stub, `docs_pages` empty under `VISUAL_PATH=degraded`) and router p95 ≤400 ms
(vLLM); both re-run at GPU provisioning via `eval/run_eval.py --retrieval-only`
and `eval/router_report.py`.

- **Query intent router** (task 1): `app/router/` — `IntentRouter.classify()` →
  `text | visual | metadata | multi_doc`. The LLM call (few-shot DE+EN, JSON-only,
  `INTENT_ROUTER_SYSTEM` in the central prompts module) rides the classification model
  (`llm_class_model`, Qwen2.5-3B role, via `get_class_llm()`); everything around it is
  deterministic — closed-set validation, and ANY failure (unreachable backend, bad JSON,
  unknown label, empty query) falls back to `text` (spec). Labeled set
  `eval/router_labeled.jsonl` (72 queries, DE+EN, incl. traps: table→text,
  content-when vs property-when, single-chart comparisons→visual);
  `tests/test_router.py` gates accuracy ≥90% (marker `llm`, like `docling`) and asserts
  p95 ≤400 ms only on vLLM (dev CPU exempt, Phase 1 exception). **Decision (flag at
  gate):** the new 4-intent taxonomy SUPERSEDES the legacy 9-category router; the graph
  no longer consumes `ROUTES` (kept only for `LLMClient.route()` rollback); the old
  "unsupported" dead-end class is gone (small models over-used it; every intent now ends
  in a document-grounded answer attempt). `route` in API/audit carries the intent.
- **Metadata path** (task 2): `metadata` intent → `app/retrieval/metadata_lookup.py`,
  a deterministic ACL-scoped Postgres lookup (filename/collection keyword narrowing with
  hyphen-compound handling, file-type filter, newest-first, `metadata_max_documents`),
  rendered as `type=metadata` chunks in the question's language (Rule 8); no hits → the
  graph falls back to normal retrieval (spec: "then optional retrieval"); hits skip the
  LLM relevance grader (deterministic ≠ gradeable). **Decision (flag at gate):** the
  spec's "author" facet needs data that didn't exist — added nullable
  `documents.uploaded_by_id` (migration `f3a9c1d24e57`, FK users SET NULL), set on
  upload, **backfilled from the audit log's UPLOAD entries**; pre-audit rows render
  "unbekannt/unknown".
- **Visual retrieval** (task 3): `app/retrieval/visual.py` — query → `colqwen`
  `/embed_query` (client shared with ingestion) → Qdrant `docs_pages` MAX_SIM
  multivector query with the ACL filter INSIDE the query (Rule 5), capped
  `visual_top_k_pages=4` (spec). Degrades to [] (never errors) when the visual path is
  degraded (dev), the service is down, or the collection is absent.
  `app/retrieval/fusion.py` RRF-merges (k=60) the reranked text list and the MAX_SIM
  page list into the assembler's packing order; ties resolve text-first. The graph
  runs page retrieval alongside text-hybrid for `visual` intent only.
- **Context assembler** (task 4): `app/context/assembler.py` — the LAST gate before the
  generator: ACL re-verification (drops + CRITICAL log; defense in depth — a drop here
  means a Rule 5 bug upstream), hard token budget (`context_token_budget`, chunker's
  estimator; oversized first block truncated rather than starving), ≤`context_max_images`
  page images with MinIO s3://→base64 resolved ONLY here, and `packed_chunks` as the
  exact [n]-citation source of truth (citations now map against the packed context, not
  the raw retrieval set). Images are never persisted into graph state (checkpointer
  bloat); generator passes `max_images=0` until the Phase 4 VLM contract consumes them
  (loading MinIO images for a text-only model would be dead I/O per visual turn — the
  budget mechanics are fully unit-tested under adversarial input, per DoD).
- **Semantic cache scope-hash key** (task 5, closes AUDIT F1/F4 + §11 eviction):
  entries now carry the ASKER's full ACL-scope hash; lookup filters on scope-hash
  equality INSIDE the Qdrant query. **Decision (flag at gate):** this is STRICTER than
  the old subset rule — a superset-privileged user no longer shares a narrower user's
  entries (hit rate pays for hard scope isolation; same-scope repeats, the common case,
  still hit). Pre-Phase-3 entries (no scope_hash) are never served — safe migration,
  cold cache. Subset source check kept as an independent second barrier. Expired
  entries: opportunistic delete on lookup + `purge_expired()` swept by the worker every
  `semantic_cache_purge_interval_s`. Hit/miss metrics were already exported
  (`record_cache`); threshold already configurable.
- **Retrieval eval** (task 6): `/search` gained `include_pages` (visual-path results in
  the response; empty when degraded); `eval/run_eval.py` scores `visual_hit@5` for
  chart/diagram/scanned/table cases against ground-truth (doc, page) targets and reports
  it in the aggregate. Visual quality numbers are **GPU-deferred** (dev colqwen is the
  deterministic stub; `docs_pages` is empty under `VISUAL_PATH=degraded`) — same
  deferral shape the operator accepted in Phases 1–2.
- **Incidental fixes** (separate commits): openai pin 1.54→1.58 (1.54 + httpx 0.28
  crashes at client construction — masked until Phase 3 made real in-container LLM
  calls); alembic `fileConfig(disable_existing_loggers=False)` (in-process migrations
  silenced all app loggers); citations now propagate `file_name` (AUDIT §11 deferral).
- **ROLLBACK:** every Phase 3 feature is additive and env-gated. Router mis-routing
  degrades to `text` by construction; visual path off = `VISUAL_PATH=degraded` (dev
  default); cache reverts by clearing the `semantic_cache` collection (entries are
  disposable). The migration is backward-compatible (nullable column, SET NULL FK).

## Phase 2 — Multimodal ingestion pipeline (gate: "PHASE 2 APPROVED", 2026-07-04)

> Gate ratified all three flagged decisions: (1) BLPOP worker extended instead of arq/rq
> rewrite, (2) captioning via the `vlm` service `POST /caption` superseding the 501 stub,
> (3) GPU deferrals (caption quality, ColQwen2 retrieval quality, real-corpus volume run)
> measured at GPU provisioning.

- **MinIO object store** (task 1): digest-pinned service in both stacks, internal-network-only
  in prod, SSE-S3 on for every object (`MINIO_KMS_AUTO_ENCRYPTION=on`, verified by header
  assertion in `tests/test_object_store.py`). Client: `app/ingestion/object_store.py`
  (spec bucket layout, internal `s3://` URIs, no presigned/public URLs ever — Rule 5).
- **Semantic chunker** (task 3): `app/ingestion/chunker.py` — 350–600-token windows,
  15 % overlap, heading-bounded; tables → GitHub-MD chunk + deterministic one-line summary
  + row-serialized chunks (>8 rows); never whitespace-flattened.
- **Queue-driven workers** (task 6): `ingest_jobs` Postgres table (migration `d91a4b7f02e1`),
  worker advances QUEUED→PARSING→INDEXING→INDEXED/FAILED, retries reuse the job row,
  permanent failures dead-letter to `ingest:dlq` with admin-requeue helper
  (`app/ingestion/jobs.py`). **Design decision (spec said "e.g. arq or rq"):** the existing
  BLPOP worker was EXTENDED, not replaced — it already provided the Redis queue +
  content-hash idempotency; the spec's remaining requirements (resumable, DLQ, Postgres
  progress) were added surgically. A framework rewrite would have violated the brownfield
  rule (Rule: no rewrite of working modules without operator approval) for zero property gain.
  Operator ratifies this choice at the Phase 2 gate.
- Spec module-name mapping: `ingest/parser.py|chunker.py|figures.py|pages.py` →
  `app/ingestion/docling_parser.py|chunker.py|figures.py|pages.py` (consistent with the
  existing package layout).
- **Figure pipeline** (task 4): `app/ingestion/figures.py` + indexer `figure_sink` — each
  Docling figure crop is uploaded to MinIO (`figures/{doc_id}/{figure_id}.png`), captioned via
  the `vlm` service `POST /caption` (Qwen2.5-VL-7B, fixed DE/EN prompt: description, axis/legend
  values, visible text/OCR, trends), and becomes a `type=figure` chunk carrying `image_uri`.
  A figure appearing flips the job to CAPTIONING. **Decision:** captioning reuses the existing
  worker→`vlm` service boundary (CLAUDE.md §10: the 501 stub is *superseded* by the captioner),
  not a parallel endpoint. The `vlm` service now serves `/caption` with a deterministic,
  clearly-labelled `[STUB-Caption]` stub in dev/CPU and the real model when `VLM_IMPLEMENTED=true`
  on the GPU host. Captioning never raises — any failure degrades to the document's own caption.
  **Flagged deferral (like Phase 1 load):** dev keeps `VISUAL_PATH=degraded` (figures retain
  document captions; MinIO upload + `image_uri` still exercised end-to-end), so the Phase 2
  caption-quality DoD gate (≥85 % useful) is measured on the GPU host, not the CPU dev stack.
- **Page-image pipeline** (task 5): `app/ingestion/pages.py` renders each PDF page to a PNG
  ≤1024 px (PyMuPDF, CPU) → MinIO `pages/{doc_id}/{page_no}.png` → ColQwen2 multivector via the
  new `colqwen` service → Qdrant `docs_pages` (`app/ingestion/pages_index.py`): multivector
  collection, `MAX_SIM` comparator, **binary quantization ON**, ACL payload with the SAME
  `collection_id`/`document_id` keys as the text schema (Rule 5). Indexer runs the page pass for
  PDFs when `visual_path == "full"`, best-effort (a page failure never fails the text ingest).
  `colqwen` service: deterministic `[stub]` multivector in dev/CPU, real `vidore/colqwen2-v1.0`
  (colpali-engine) when `COLQWEN_IMPLEMENTED=true` on the GPU host. Idempotency hardened: the
  indexer now clears Postgres + Qdrant + MinIO for a document BEFORE re-parsing, so re-ingest
  with a changed figure/page count leaves zero orphans. Visual retrieval quality (ColQwen2
  embeddings need a GPU) is a Phase 3/GPU-host concern; the dev stub proves the index wiring.
- **Gate tests + sampling harness** (task 8): `app/ingestion/acl_audit.py` scans a Qdrant
  collection for any object missing the `collection_id`/`document_id` ACL payload (Rule 5),
  reused by the Phase 5 red-team. Automated CI gates (`tests/test_ingest_gates.py`):
  re-ingesting an unchanged document creates ZERO new vectors (idempotency), and 100 % of
  indexed objects carry the ACL payload. `eval/ingest_sample.py` emits a side-by-side HTML
  report (rendered page image next to extracted text/table/figure chunks) for manual table-
  fidelity (≥90 %) and caption-usefulness (≥85 %) review. **docs_pages storage measured:**
  MAX_SIM multivector + binary quantization (`always_ram`) confirmed active — ~32× vs float32
  (400 KB → 12.5 KB for 50 pages × 16 patches × 128 dims).
- **Admin UI ingestion status** (task 7): `GET /documents/{id}/ingest-status` (ACL-scoped) exposes
  the latest `ingest_jobs` row; the React Documents view shows the fine-grained pipeline stage
  (queued/parsing/captioning/indexing/indexed/failed), attempt count, a re-ingest button, and the
  failure reason inline on failed rows. `tsc --noEmit` clean; backend endpoint tested incl.
  cross-ACL 404.

## Phase 1 — Serving migration: Ollama → vLLM (in progress, 2026-07-02)

- **Single LLM client module** (spec location): `app/graph/llm.py` → `app/llm/client.py`.
  No behavior change; all callers (graph builder/nodes/runtime, eval judge) updated.
  There were no Ollama-specific code paths to remove — the client has always been
  OpenAI-compatible and backend-agnostic (documented no-op for spec task 2b).
- **`LLM_BACKEND` setting** (`ollama | vllm`, typed Literal): names the serving backend for
  ops/health/degradation messages. Prod compose sets `vllm`, dev sets `ollama` (default).
- **Graceful degradation:** `/chat` and `/chat/stream` fail fast with
  `503 "LLM backend (<name>) is unavailable — please try again shortly"` when the backend is
  unreachable (cached 5s TCP probe, `app/llm/client.py::llm_available`), instead of running the
  graph into silent empty answers. `/health/ready` now reports an `llm:<backend>` dependency.
  Verified live: stopped Ollama → 503 with the exact message; restarted → healthy.
- **Compose digest pins applied** (from `docs/PINS.md`, resolved 2026-07-02): postgres, redis,
  qdrant, phoenix, **vllm/vllm-openai** (DoD-critical), nginx, ollama(dev). Dockerfile base
  pins remain recorded-only until CI exists.
- **ROLLBACK (one step):** point the backend at the previous serving backend via env only —
  `LLM_BACKEND=ollama`, `LLM_BASE_URL=http://ollama:11434/v1`, `LLM_GEN_MODEL=<ollama tag>`
  (and `LLM_CLASS_MODEL`) — then `docker compose up -d backend worker`. No code change; both
  backends speak the OpenAI API. (Dev stack ships this configuration by default.)
- **Flagged deviation (operator decision at gate):** dev compose KEEPS the Ollama service —
  the dev host is CPU-only and the official vLLM image requires CUDA. Prod compose serves
  vLLM exclusively and contains no Ollama. True vLLM parity eval + 50-user load targets can
  only be measured on the prod GPU host during provisioning.

## Phase 0 — Audit & baseline (gate: "PHASE 0 APPROVED", 2026-07-02)

- `docs/AUDIT.md`: full module map, ACL enforcement path + sequence diagram, endpoint sweep
  (zero cloud endpoints), findings F1–F4 (retrieval-ACL) and F5–F8 (discovered during Phase 0,
  remediated: refresh-token revocation bypass, upload path traversal, unauthenticated
  /metrics/summary, worker heartbeat staleness).
- `docs/PINS.md`: lockfiles committed (backend 101 pkgs exact, services, npm lockfileVersion 3);
  image digests resolved; model HF-revision pins open (operator provisioning, Phase 1).
- `eval/golden_v2.jsonl`: 130 QA pairs (100 text + 30 visual, DE+EN) + `eval/run_eval.py`
  harness (hit@k, citation accuracy, LLM-judge) + synthetic DE/EN fixture corpus.
- `eval/reports/baseline.md`: 130 cases, text judge 42.1% / hit@5 73.9%; visual near-zero
  (chart 0.0%, diagram 0.0%, table 11.7%) — the intended migration baseline.
- Out-of-scope edits reverted; insights preserved in `docs/AUDIT.md` §11 (deferred observations).
