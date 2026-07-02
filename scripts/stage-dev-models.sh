#!/usr/bin/env bash
# One-time DEV model staging (setup-time network access only — distinct from the
# air-gapped-at-RUNTIME guarantee). Pulls the small dev generation model into the
# already-running Ollama container so the agent graph has a model to call.
#
# Usage (after `docker compose -f docker-compose.dev.yml up -d`):
#   bash scripts/stage-dev-models.sh
#
# Prod does NOT use this: prod mounts pre-staged weights into the vLLM/VLM
# containers with zero runtime fetch.
set -euo pipefail

MODEL="${LLM_GEN_MODEL:-qwen2.5:3b}"
SERVICE="${OLLAMA_SERVICE:-ollama}"

echo ">> Pulling dev model '${MODEL}' into the '${SERVICE}' container..."
docker compose -f docker-compose.dev.yml exec "${SERVICE}" ollama pull "${MODEL}"

echo ">> Staged models:"
docker compose -f docker-compose.dev.yml exec "${SERVICE}" ollama list

echo ">> Done. Dev LLM is ready at http://localhost:11434/v1"
