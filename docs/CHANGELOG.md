# CHANGELOG — Multimodal RAG Migration

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
