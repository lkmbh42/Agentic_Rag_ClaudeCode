# Development vs Production

Two **self-contained** Compose files. There is no merge/override layering — each
file runs the whole stack on its own, so the laptop command is exactly one line.

| | Development | Production |
|---|---|---|
| Command | `docker compose -f docker-compose.dev.yml up` | `docker compose up -d` |
| Host | Windows 11 laptop, Docker Desktop + WSL2 | Company server + NVIDIA Container Toolkit |
| GPU | None (CPU) | Single ~24 GB NVIDIA GPU |
| LLM serving | `ollama` (Qwen2.5-3B, CPU) | `vllm` single instance (Qwen2.5-7B-AWQ, GPU) |
| LLM endpoint | `http://ollama:11434/v1` | `http://vllm:8000/v1` |
| Classification/grading | same Ollama model | same vLLM model, constrained JSON + priority scheduling |
| Visual path | **degraded** (OCR + marker), no `vlm` service | **full**, `vlm` on CPU at ingest |
| Embeddings device | `cpu` | `cuda` |
| Reverse proxy | none (services exposed directly) | `proxy` (nginx) in front of backend + admin-ui |
| Source | bind-mounted + `--reload` | baked into image, no reload |
| Models | staged once via `scripts/stage-dev-models.sh` (setup-time) | **pre-mounted**, zero runtime download |
| Restart policy | none | `unless-stopped` |

## The one line of code that changes between environments

Nothing in `app/` branches on environment for model serving. Both Ollama and
vLLM speak the OpenAI API, so only `LLM_BASE_URL` (and the model id) differ —
set via `.env` / compose `environment`. The agent graph code is identical.

## Air-gapped boundary

- **Runtime (prod):** no external calls. Weights are mounted from `${MODELS_DIR}`;
  vLLM/VLM never download. Phoenix, embeddings, reranker, judge — all local.
- **Setup-time (dev only):** pulling base images and running
  `scripts/stage-dev-models.sh` (Ollama model pull) uses the network **once**.
  This is explicitly not part of the runtime air-gap guarantee.

## GPU / VRAM (24 GB prod target — ADR 0.5)

| Component | VRAM | Knob (`.env`) |
|---|---|---|
| `vllm` (Qwen2.5-7B-AWQ, gen+class+judge) | ~17 GB | `VLLM_GPU_MEMORY_UTILIZATION`, `VLLM_MAX_NUM_SEQS`, `VLLM_MAX_MODEL_LEN` |
| `embeddings` (BGE-M3 + reranker) | ~4 GB | `EMBEDDINGS_DEVICE` |
| `vlm` (Qwen2.5-VL-7B) | 0 GB (CPU) | `VLM_DEVICE` |
| **Total resident** | **~21 GB / 24 GB** | |

If you hit CUDA OOM: lower `VLLM_GPU_MEMORY_UTILIZATION` (e.g. 0.65), then
`VLLM_MAX_NUM_SEQS`, then `VLLM_MAX_MODEL_LEN`. Full tuning guide lands in Phase 8.

## Health checks (Phase 1 DoD)

Every service defines a healthcheck so `docker compose ps` shows `healthy`:

| Service | Check |
|---|---|
| postgres | `pg_isready` |
| redis | `redis-cli ping` |
| qdrant | TCP connect on 6333 (bash `/dev/tcp`) |
| phoenix | HTTP GET `:6006` (python urllib) |
| ollama (dev) | `ollama list` |
| vllm (prod) | HTTP GET `/health` |
| embeddings | HTTP GET `/health` |
| vlm (prod) | HTTP GET `/health` |
| backend | HTTP GET `/health` |
| worker | heartbeat-file freshness |
| admin-ui / proxy | HTTP GET `/healthz` |
