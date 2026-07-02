# Shared image for the FastAPI backend and the background worker.
# Same dependency set; the compose `command` selects which process runs.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# tesseract-ocr binary is required by pytesseract (scanned-PDF / image OCR).
# PyMuPDF/pdfplumber/Pillow ship wheels, so no other system libs are needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# psycopg2-binary + bcrypt ship wheels, so no compiler toolchain is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source. app/ is imported by both processes (worker reads app.config).
COPY app/ ./app/
COPY worker/ ./worker/

# Non-root runtime user. /data is the shared uploads volume mount point; owning
# it in the image makes the named volume inherit appuser ownership on first init.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /srv /data
USER appuser

EXPOSE 8000

# Default = API. The worker service overrides this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
