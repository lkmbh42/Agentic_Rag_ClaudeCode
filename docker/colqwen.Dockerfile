# ColQwen2 visual-retrieval service (Phase 2). Slim FastAPI stub by default;
# the GPU-host build adds colpali-engine + torch (COLQWEN_IMPLEMENTED=true).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY services/colqwen/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/colqwen/ ./services/colqwen/

RUN useradd --create-home --uid 10004 appuser \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8003

CMD ["uvicorn", "services.colqwen.main:app", "--host", "0.0.0.0", "--port", "8003"]
