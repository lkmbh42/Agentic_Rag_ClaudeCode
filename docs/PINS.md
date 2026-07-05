# PINS.md — Dependency & Image Pin Inventory (Phase 0)

Resolved 2026-07-02 from the upstream registries. Phase 0 write-path rules forbid editing
compose files / Dockerfiles / requirements files, so the pins are **recorded** here; applying
them (compose `image:` digest refs, `npm ci`, `pip install -r requirements.lock`) is the
first change of Phase 1.

## 1. Python lockfiles (committed)

| Lockfile | Source image | Notes |
|---|---|---|
| `requirements.lock` | `agentic-rag-dev-backend` (built from `docker/backend.Dockerfile`, `python:3.11-slim`) | backend + worker runtime deps, 101 packages, exact `==` versions |
| `services/embeddings/requirements.lock` | `agentic-rag-dev-embeddings` (stub build, `INSTALL_MODELS` unset) | **stub-mode freeze** — does NOT include `FlagEmbedding`/`torch` from `requirements-prod.txt`; a prod-build freeze (`INSTALL_MODELS=true`) must be captured on the GPU host during Phase 1 provisioning |
| `services/vlm/requirements.lock` | `agentic-rag-dev-vlm` (built from `docker/vlm.Dockerfile`) | stub service; real captioner deps arrive with the Phase 2 replacement |

Reproduce: `docker run --rm <image> pip freeze > <lockfile>`.

## 2. Node lockfile (committed)

`admin-ui/app/package-lock.json` — generated with `npm install --package-lock-only --ignore-scripts`
(npm 11 / lockfileVersion 3). `docker/admin-ui.Dockerfile` currently runs `npm install`; switch to
`npm ci` in Phase 1 so the lockfile is authoritative.

⚠️ `npm install` reported **2 vulnerabilities (1 moderate, 1 high)** in the resolved tree.
Full `npm audit` / `pip-audit` is Phase 5 scope; recorded here so it is not lost.

## 3. Docker image digests (compose pins APPLIED in Phase 1)

Compose references are digest-pinned as `image: <name>:<tag>@<digest>` since Phase 1.
Dockerfile base-image digests remain recorded-only (applying them forces full image rebuilds;
scheduled with the first CI setup).

| Reference | Where | Digest | Status |
|---|---|---|---|
| `postgres:16-alpine` | compose (prod+dev) | `sha256:e013e867e712fec275706a6c51c966f0bb0c93cfa8f51000f85a15f9865a28cb` | ✅ pinned in compose (Phase 1) |
| `redis:7-alpine` | compose (prod+dev) | `sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99` | ✅ pinned in compose (Phase 1) |
| `qdrant/qdrant:v1.12.4` | compose (prod+dev) | `sha256:241edb9d7778327516ef218f8c74e1bd61b5ea42cd4f193cb8d0896199705636` | ✅ pinned in compose (Phase 1) |
| `arizephoenix/phoenix:latest` | compose (prod+dev) | `sha256:45a2dbd623d12f9924dc3d554a3f35574764541d7375d081787f0e06e4d3f2fa` | ✅ pinned in compose (Phase 1) |
| `vllm/vllm-openai:latest` | compose (prod) | `sha256:251eba5cc7c12fed0b75da22a9240e582b1c9e39f6fbc064f86781b963bd814f` | ✅ pinned in compose (Phase 1, DoD-critical) |
| `ollama/ollama:latest` | compose (dev) | `sha256:f1a705f2bd113fb8d15f85f7c217f0dc5f6bebda6b0cc42b82c3ad165ffcb9dc` | ✅ pinned; ⚠️ service KEPT in dev (CPU-only dev host — flagged Phase 1 gate deviation; prod has no Ollama) |
| `nginx:1.27-alpine` | compose (prod) + `docker/admin-ui.Dockerfile` | `sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` | ✅ pinned in compose; Dockerfile ref recorded-only |
| `minio/minio:RELEASE.2025-04-22T22-12-26Z` | compose (prod+dev), NEW in Phase 2 | `sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e` | ✅ pinned from first use (resolved 2026-07-03) |
| `prom/prometheus:v2.54.1` | compose (prod), NEW in Phase 5 | `sha256:f6639335d34a77d9d9db382b92eeb7fc00934be8eae81dbc03b31cfe90411a94` | ✅ pinned from first use (resolved 2026-07-05) |
| `grafana/grafana:11.2.0` | compose (prod), NEW in Phase 5 | `sha256:408afb9726de5122b00a2576763a8a57a3c86d5b0eff5305bc994ceb3eb96c3f` | ✅ pinned from first use (resolved 2026-07-05) |
| `python:3.11-slim` | `docker/{backend,embeddings,vlm}.Dockerfile` | `sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6` | recorded-only (CI setup applies) |
| `node:20-alpine` | `docker/admin-ui.Dockerfile` (build stage) | `sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293` | recorded-only (CI setup applies) |

Digests are multi-arch manifest-list digests (`docker buildx imagetools inspect`), valid for
`image@digest` references on any platform.

## 4. Model pins (open — operator provisioning)

No model reference in the repo carries an HF revision hash (see `docs/AUDIT.md` §7). The
`CLAUDE.md` model manifest `<HF_REVISION_HASH>` placeholders must be filled by the operator
during Phase 1 provisioning; CI enforcement ("no placeholder remains") lands with the first CI
setup (none exists today).

Phase 2 adds one entry to the manifest:

| Role | Model | Serving | Pin |
|---|---|---|---|
| Layout + TableFormer (Docling) | `ds4sd/docling-models` | in-process (worker), staged via `scripts/stage-docling-models.sh` → `DOCLING_ARTIFACTS_PATH` | `<HF_REVISION_HASH>` (operator; script warns loudly when unpinned — dev-only) |

### Phase 4 — answer-model configurations (operator decision, ratified at the Phase 4 gate)

The serving stack is fully env-parameterized; which answer model runs is a `.env`
decision on the GPU host, not a code change:

| Configuration | Model | VRAM | Status |
|---|---|---|---|
| **ADR default (24 GB)** | `Qwen/Qwen2.5-7B-Instruct-AWQ` (text) + `LLM_MULTIMODAL=false` — visual questions answer from pre-computed captions (ADR 0.3: zero query-time VLM calls) | ≈21 GB resident incl. embeddings | active default |
| CLAUDE.md manifest (≥48 GB) | `Qwen/Qwen2.5-VL-32B-Instruct-AWQ` + `LLM_MULTIMODAL=true` — mixed text+image context per Phase 4; router/graders move to a second small vLLM (two-vLLM topology, ADR 0.5 tuning note) | does NOT fit 24 GB | documented overlay in `.env.example` |

Both models get `<HF_REVISION_HASH>` pins at provisioning like every other model.
Whatever model serves generation must pass the golden text subset ≥ Phase 1 score
BEFORE go-live (CLAUDE.md Phase 4 task 1 parity gate — GPU-host step).
