# ADR — Agentic RAG Platform (v1)

Status: **Approved (Phase 0 complete)** · Date: 2026-06-22

This Architecture Decision Record pins every load-bearing decision for the platform.
No application code is written until this ADR is approved. The Phase 1 Docker service
list is derivable directly from this document.

## Hardware targets (the assumption everything else hangs off)

| Environment | Hardware | Role |
|---|---|---|
| **Development** | Windows 11 laptop, **no/uncertain NVIDIA GPU**, Docker Desktop + WSL2 backend | Build & iterate; reduced concurrency; CPU-only model serving; seed/test data |
| **Production** | Company server, **single ~24 GB NVIDIA GPU** | ~50 concurrent employees; air-gapped at runtime |

The **24 GB single-GPU** production target is the dominant constraint and is the reason
for several decisions below (single vLLM instance, 7B generation model, CPU/ingest VLM).

---

## 0.1 — Model serving strategy

**Topology: ONE vLLM instance serving every LLM call-site**, plus a throttled background
judge on that same instance.

On a single 24 GB GPU, running two vLLM instances would split the KV-cache pool and
*reduce* the concurrency available to 50 users. A single instance is memory-optimal.
Head-of-line blocking (cheap router/grader calls stuck behind long generations) is
mitigated by **vLLM priority scheduling** (short structured calls jump the queue) and
**continuous batching** (they run alongside generations in the same batch, not strictly
behind them).

| Role / graph node | Model | Output format | Notes |
|---|---|---|---|
| Generator, Planner | **Qwen2.5-7B-Instruct (AWQ 4-bit)** | Free text + citations; **SSE streamed** | Apache-2.0; strong RAG/JSON; ~5 GB weights leaves room for KV cache |
| Router | same model | **Constrained JSON** (guided decoding / xgrammar) | High priority in scheduler |
| Retrieval Grader | same model | **Constrained JSON** | High priority |
| Hallucination Grader | same model | **Constrained JSON** | High priority |
| Judge (eval worker) | same model | **Constrained JSON** scores | Worker-side **concurrency cap = 2**, off critical path, never starves interactive |

**Why not a separate 1–3B classification model:** on 24 GB it would consume KV-cache
budget for marginal latency gain, and constrained decoding on the 7B is *higher* quality
for the structured nodes. Two-container split is the **upgrade path at 48 GB+**.

**Concurrency ceiling (honest):** ~10–15 truly in-flight generations comfortably. 50
logged-in users with normal think-time is feasible; 50 simultaneous submits will queue
and p95 will rise. **Per-user quotas + queue-depth/queue-wait metrics** keep this bounded
and visible. Validated, not assumed, in the Phase 8 load test.

**Dev (laptop, no GPU):** single **Ollama** container (Qwen2.5-3B, OpenAI-compatible),
CPU-only, low concurrency, fills both generation and classification roles. Same OpenAI
client code as prod — only `base_url` differs, so the graph code is identical dev↔prod.

### Model-routing table (graph node → model → format)

| Node | Model (prod) | Model (dev) | Format |
|---|---|---|---|
| Router | Qwen2.5-7B-AWQ | Qwen2.5-3B (Ollama) | constrained JSON |
| Planner | Qwen2.5-7B-AWQ | Qwen2.5-3B | free text plan (bounded steps) |
| Generator | Qwen2.5-7B-AWQ | Qwen2.5-3B | free text + citations, SSE |
| Retrieval Grader | Qwen2.5-7B-AWQ | Qwen2.5-3B | constrained JSON |
| Hallucination Grader | Qwen2.5-7B-AWQ | Qwen2.5-3B | constrained JSON |
| Judge (worker) | Qwen2.5-7B-AWQ | Qwen2.5-3B | constrained JSON |

---

## 0.2 — Embedding & retrieval models

| Component | Decision | Rationale |
|---|---|---|
| Embedding model | **BGE-M3** (1024-d dense, max seq 8192, multilingual) | One model emits dense + learned-sparse (+ColBERT); collapses two serving concerns into one. 8k context handles large table/section chunks. |
| Serving | Dedicated **`embeddings` container** (Infinity, model mounted, offline), exposes dense + sparse over HTTP | Keeps embedding off the LLM GPU critical path; batched ingest throughput |
| Sparse strategy | **BGE-M3 learned sparse (lexical weights)** → Qdrant `sparse` vector | Free from the same model; no separate SPLADE/BM25 pass; single source for the collection schema |
| Reranker | **Yes — bge-reranker-v2-m3** cross-encoder, after RRF (top-k≈20 → top-n≈5) | Hybrid+RRF maximizes recall; cross-encoder fixes precision@k, which is what the generator consumes. Co-located in `embeddings` container (~+1 GB) |

**Qdrant collection schema:** named vectors `dense` (1024-d, cosine) + `sparse`
(BGE-M3 lexical); per-point payload carries the full per-chunk schema incl. **ACL
metadata** for query-time filtering.

---

## 0.3 — Vision model (VLM)

**Decision: full visual path retained, VLM runs on CPU at ingest time** (prod 24 GB);
degraded path in dev and as prod fallback.

| Aspect | Decision |
|---|---|
| Prod path (24 GB) | **Full path, CPU-only at ingest.** `vlm` container (Qwen2.5-VL-7B) summarizes charts/diagrams and captions images during background ingestion. **0 GB GPU** — preserves all GPU for interactive traffic. |
| Why CPU is acceptable | Ingest is async/batch, off the user critical path. Slow CPU summarization (tens of seconds/visual) creates an indexing backlog we **monitor** (indexing-backlog metric), not user-facing latency. |
| Query-time cost | **Zero VLM calls at query time.** `chart_question` / `diagram_question` / `image_question` router branches retrieve pre-computed visual summaries. |
| Dev path | **Degraded** (OCR text + bbox + page ref + `"visual — not interpreted"` marker), cited honestly. No VLM on the laptop. |
| Fallback | Degraded path in prod too, if CPU ingest backlog proves unacceptable. |
| Upgrade path | Move VLM to GPU (resident or low-traffic-window scheduled) when hardware grows to 48 GB+. No schema change — `chunk_type` + payload already support it. |

**Honesty rule (enforced in the generator):** if a visual could not be fully
interpreted, the stored chunk still carries a description + page ref, and the answer
cites it as an uninterpreted visual rather than fabricating its contents.

---

## 0.4 — Admin UI

Committed for v1 (not a placeholder): **React + Vite + TypeScript SPA, shadcn/ui**, built
to static assets, served by **nginx in its own `admin-ui` container** behind the reverse
proxy, authenticating to existing FastAPI endpoints via JWT. Consumes only the documented
API — **no privileged backdoor endpoints**; every admin action is an ordinary
`role=admin` RBAC-gated call.

**Effort impact:** adds the `admin-ui` service and a dedicated **Phase 9** (auth flow +
6 screens: user/org mgmt, permissions grant/edit/revoke, collection/document mgmt with
indexing-status + retry + delete/re-version, audit-log viewer, eval-metrics viewer,
live-ops dashboard).

**Alternative considered & not chosen:** server-rendered admin via FastAPI + Jinja —
fewer moving parts but weaker for live-ops views and couples admin to the API.

---

## 0.5 — Cross-cutting decisions

| Decision | Pinned value |
|---|---|
| DB migrations | **Alembic**, mandated from Phase 2; includes LangGraph Postgres checkpointer tables |
| Streaming | **Yes — SSE token streaming on `POST /chat`.** Generator streams via LangGraph `astream_events`; cache-hit and "insufficient evidence" paths emit a single terminal event. Eval-queue dispatch stays async/non-blocking. |
| JWT revocation | **Short-lived access tokens (15 min) + refresh-token rotation, backed by a Redis `jti` denylist** for immediate forced logout. Rotation is steady-state; the denylist makes admin **suspend** / **revoke-sessions** take effect immediately (required by Phase 9 DoD). |

### VRAM budget — single 24 GB GPU (production)

| Component | Model / precision | GPU VRAM | Notes |
|---|---|---|---|
| `vllm` (single) | Qwen2.5-7B-Instruct **AWQ** (gen + router + graders + judge) | ~5 GB weights + ~12 GB KV ≈ **17 GB** | `gpu_memory_utilization≈0.72`; `max_num_seqs` + priority scheduling tuned in Phase 8 |
| `embeddings` | BGE-M3 + bge-reranker-v2-m3 | ≈ **4 GB** | resident; every query needs it |
| `vlm` | Qwen2.5-VL-7B | **0 GB GPU** | CPU at ingest |
| **Total GPU resident** | | **≈ 21 GB** | Fits on 24 GB, ~3 GB headroom |

**Tuning notes:** On **48 GB**, move to two-vLLM topology (separate fast-classification
model), upgrade generation to 14B-AWQ or FP16, raise KV/`max_num_seqs`, and make the VLM
GPU-resident. On **80 GB**, generation FP16 + large KV. Peak interactive GPU on 24 GB is
gen + embed ≈ 21 GB; VLM ingest is CPU so it never contends for VRAM.

---

## Windows 11 laptop dev — addendum

| Concern | Decision |
|---|---|
| Container runtime | Docker Desktop, **WSL2 backend**; all services are Linux containers. `docker compose -f docker-compose.dev.yml up` = one-command startup. |
| Line endings | `.gitattributes` forces **LF** on `*.sh`, entrypoints, Dockerfiles (CRLF breaks container entrypoints). |
| Dev LLM | **Ollama** container (Qwen2.5-3B), CPU-only; uses WSL2 CUDA passthrough automatically only if a GPU is later present. |
| Visual path | **Degraded** on the laptop (no VLM). |
| Model acquisition | Dev = one-time documented setup step to stage models. Prod = pre-staged files **mounted**, **zero runtime fetch** (air-gapped at runtime). Separate code paths. |
| Paths/volumes | WSL2-friendly relative paths in Compose; no hard-coded `C:\` paths. |

---

## Docker service list (Phase 1 input — derived from this ADR)

`fastapi-backend` · `worker` (indexing + eval) · `admin-ui` (nginx, Phase 9) ·
`vllm` (single, prod) · `vlm` (CPU/ingest) · `embeddings` (BGE-M3 + reranker) ·
`qdrant` · `postgres` · `redis` · `phoenix` · *(dev only)* `ollama` ·
*(prod)* reverse proxy.

---

## Phase 0 exit criteria — status

- [x] 0.1 model serving strategy — pinned (single vLLM, 7B-AWQ, constrained JSON, priority scheduling)
- [x] 0.2 embedding/retrieval — pinned (BGE-M3 dense+sparse, reranker)
- [x] 0.3 VLM path — pinned (full path, CPU/ingest)
- [x] 0.4 admin UI — pinned (React/Vite SPA, Phase 9)
- [x] 0.5 cross-cutting — pinned (Alembic, SSE, JWT denylist, VRAM table)
- [x] Phase 1 Docker service list derivable

Each decision has a chosen value, alternatives considered, and rationale.
