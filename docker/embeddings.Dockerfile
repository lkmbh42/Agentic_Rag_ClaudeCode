# Embeddings + reranker service.
# Phase 1: slim FastAPI stub. Phase 4 swaps in the BGE-M3 / FlagEmbedding stack
# (and a CUDA base image for the GPU prod profile).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# INSTALL_MODELS=true -> prod image with FlagEmbedding + torch (BGE-M3 + reranker).
# default (false) -> slim stub image used in dev.
ARG INSTALL_MODELS=false

COPY services/embeddings/requirements.txt services/embeddings/requirements-prod.txt ./
RUN if [ "$INSTALL_MODELS" = "true" ]; then \
        pip install --no-cache-dir -r requirements-prod.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY services/embeddings/ ./services/embeddings/

RUN useradd --create-home --uid 10002 appuser \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8001

CMD ["uvicorn", "services.embeddings.main:app", "--host", "0.0.0.0", "--port", "8001"]
