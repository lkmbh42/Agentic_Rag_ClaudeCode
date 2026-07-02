"""VLM HTTP service — Phase 1 stub.

Per ADR 0.3 the VLM runs the FULL visual path but CPU-only at ingest time, and
is OFF in the dev profile (degraded path: OCR + marker). This stub exists so the
prod compose has a real, health-reporting service to start; the Qwen2.5-VL-7B
implementation that summarizes charts/diagrams and captions images is delivered
in Phase 3 (ingestion).

It is called only by the worker during ingestion, never on the query path.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
DEVICE = os.environ.get("VLM_DEVICE", "cpu")
IMPLEMENTED = os.environ.get("VLM_IMPLEMENTED", "false").lower() == "true"

app = FastAPI(title="VLM (visual summarization)", version="0.1.0")


class SummarizeRequest(BaseModel):
    image_b64: str
    kind: str = "chart"  # chart | diagram | image
    page: int | None = None


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "vlm",
        "model": MODEL,
        "device": DEVICE,
        "implemented": IMPLEMENTED,
    }


@app.post("/summarize")
async def summarize(_req: SummarizeRequest) -> dict:
    if not IMPLEMENTED:
        raise HTTPException(status_code=501, detail="Qwen2.5-VL lands in Phase 3")
    raise HTTPException(status_code=501, detail="not implemented")
