# Agentic RAG Platform

A fully private, air-gapped, multi-user Agentic RAG platform for ~50 internal
employees. Self-hosted models, embeddings, vector store, observability, and
evaluation. Docker-first. Develop on a Windows 11 laptop; deploy to a GPU server.

> **Status: Phase 1 — infrastructure skeleton.** Architecture is pinned in
> [`ADR.md`](ADR.md). The stack boots healthy; application logic (auth, ingestion,
> retrieval, the agent graph) is delivered in Phases 2–9.

## Architecture at a glance

Single vLLM (Qwen2.5-7B-AWQ) serving generation + router/graders/judge via
constrained JSON; BGE-M3 hybrid dense+sparse retrieval + bge-reranker-v2-m3;
Qwen2.5-VL-7B for visual content (full path, CPU at ingest); LangGraph agent with
Postgres checkpointing; Qdrant, PostgreSQL, Redis, Phoenix. See [`ADR.md`](ADR.md)
for every pinned decision and the 24 GB VRAM budget.

## Prerequisites

- **Dev:** Windows 11 + Docker Desktop with the **WSL2 backend** enabled.
- **Prod:** Linux server + Docker + the **NVIDIA Container Toolkit** (single ~24 GB GPU).

## Quickstart — development (laptop)

```bash
# 1. Configure
cp .env.example .env            # defaults already target the dev stack

# 2. Bring up the whole stack (one command — Phase 1 DoD)
docker compose -f docker-compose.dev.yml up -d --build

# 3. Verify every service is healthy
docker compose -f docker-compose.dev.yml ps

# 4. One-time: stage the dev LLM into Ollama (setup-time network use)
bash scripts/stage-dev-models.sh
```

Then:
- Backend API + docs → http://localhost:8000/docs
- Health → http://localhost:8000/health , readiness → http://localhost:8000/health/ready
- Admin UI placeholder → http://localhost:8080
- Phoenix → http://localhost:6006
- Qdrant → http://localhost:6333/dashboard

## Quickstart — production (server)

```bash
cp .env.example .env            # then edit: secrets, LLM_BASE_URL=http://vllm:8000/v1, model paths
# Pre-stage weights into ${MODELS_DIR:-./models} (no runtime download):
#   ./models/qwen2.5-7b-instruct-awq/   (vLLM)
#   ./models/<qwen2.5-vl-7b>/           (VLM, Phase 3)
docker compose up -d --build
docker compose ps
```

App is reachable through the `proxy` service on port 80 (`/` = admin UI,
`/api/` = backend). TLS is added in Phase 8.

## Database migrations & seed (Phase 2)

```bash
# Apply migrations to the dev DB (run inside the backend image):
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
# Seed a default admin + department + sample collection:
docker compose -f docker-compose.dev.yml exec backend python -m app.seed
```

## Run the test suite (Phase 2)

Runs auth, RBAC (cross-department denial), and session-ownership tests against a
throwaway `rag_test` database (which also proves migrations apply cleanly):

```bash
docker compose -f docker-compose.dev.yml run --rm --no-deps \
  -v "$(pwd -W 2>/dev/null || pwd):/srv" backend \
  sh -c "pip install --user -q pytest pytest-asyncio && python -m pytest -q"
```

## Verify each service

```bash
docker compose -f docker-compose.dev.yml ps           # all should read "healthy"
curl -fsS http://localhost:8000/health                # backend liveness
curl -fsS http://localhost:8000/health/ready          # deps reachable
curl -fsS http://localhost:8001/health                # embeddings stub
curl -fsS http://localhost:8080/healthz               # admin-ui
docker compose -f docker-compose.dev.yml exec redis redis-cli ping
docker compose -f docker-compose.dev.yml exec postgres pg_isready -U rag
```

## Project layout

```
ADR.md                      Architecture Decision Record (Phase 0, approved)
docker-compose.yml          PRODUCTION stack (GPU, vLLM, full visual path, proxy)
docker-compose.dev.yml      DEVELOPMENT stack (CPU, Ollama, degraded visual path)
.env.example                All configurable values (copy to .env)
requirements.txt            Backend + worker deps (ML deps live per-service)
app/                        FastAPI backend
  config.py                 Pydantic settings — single source of config truth
  main.py                   App entrypoint, /health, /metrics, /metrics/summary
  health.py                 Liveness + readiness
worker/                     Background worker (indexing + eval; Phases 3/7)
services/
  embeddings/               BGE-M3 + reranker service (stub now, model in Phase 4)
  vlm/                      Qwen2.5-VL service (stub now, model in Phase 3)
admin-ui/                   nginx placeholder (React/Vite SPA in Phase 9)
docker/                     Dockerfiles + reverse-proxy config
docs/dev-vs-prod.md         Environment differences, VRAM budget, health checks
scripts/stage-dev-models.sh One-time dev model pull
```

## Phased build

| Phase | Deliverable |
|---|---|
| 0 ✅ | ADR (decisions) |
| 1 ✅ | Infra skeleton — all services boot healthy, one command |
| 2 ✅ | Backend data model, Alembic, JWT auth, RBAC (+ ACL & ownership tests) |
| 3 ✅ | Ingestion pipeline (parsing, OCR, tables, visual path, dedup, lifecycle) |
| 4 ✅ | Hybrid retrieval + reranker + permission-scoped semantic cache |
| 5 ✅ | LangGraph agent + Postgres checkpointer + circuit breakers |
| 6 ✅ | Generation + hallucination grading + corrective loop + SSE |
| 7 ✅ | Eval worker + golden set + Phoenix tracing + metrics |
| 8 ✅ | Production hardening — load test, tuning, backups, security |
| 9 ✅ | Admin UI (React/Vite/TS SPA) |

**All phases complete.** Admin UI → http://localhost:8080 (sign in with the seeded admin).

Each phase stops at its Definition of Done for approval before the next begins.
