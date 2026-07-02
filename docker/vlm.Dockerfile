# VLM service (Qwen2.5-VL-7B) — full path, CPU at ingest (ADR 0.3).
# Phase 1: slim FastAPI stub. Phase 3 adds torch(cpu) + transformers + qwen-vl-utils.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY services/vlm/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/vlm/ ./services/vlm/

RUN useradd --create-home --uid 10003 appuser \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8002

CMD ["uvicorn", "services.vlm.main:app", "--host", "0.0.0.0", "--port", "8002"]
