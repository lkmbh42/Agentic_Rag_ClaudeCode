"""ColQwen2 visual-retrieval service (Phase 2).

Encodes a page image into a per-patch MULTIVECTOR (late-interaction / MAX_SIM)
for the Qdrant `docs_pages` collection. Called only by the worker at ingest and
by the retriever at query time (Phase 3) — never public.

Two modes:
- `COLQWEN_IMPLEMENTED=true` (prod GPU host): loads `vidore/colqwen2-v1.0` via
  colpali-engine and returns real page embeddings.
- default (dev/CPU): a deterministic STUB that derives a small, image-dependent
  multivector from a hash of the PNG, so the docs_pages index + idempotency +
  ACL wiring are exercisable without a GPU. Stub vectors are L2-normalized and
  dimensioned to `COLQWEN_DIM`; they carry no semantic meaning (retrieval
  quality is a GPU-host concern).

Contract:
  POST /embed_image  {image_b64}       -> {multivector: [[float]*dim]*patches}
  POST /embed_query  {query}           -> {multivector: [[float]*dim]*tokens}
"""

from __future__ import annotations

import base64
import hashlib
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL = os.environ.get("COLQWEN_MODEL", "vidore/colqwen2-v1.0")
DEVICE = os.environ.get("COLQWEN_DEVICE", "cpu")
IMPLEMENTED = os.environ.get("COLQWEN_IMPLEMENTED", "false").lower() == "true"
DIM = int(os.environ.get("COLQWEN_DIM", "128"))
STUB_PATCHES = int(os.environ.get("COLQWEN_STUB_PATCHES", "16"))

app = FastAPI(title="ColQwen2 (visual retrieval)", version="0.1.0")

_model = None


def _load_model():  # pragma: no cover - GPU-host only
    global _model
    if _model is None:
        import torch
        from colpali_engine.models import ColQwen2, ColQwen2Processor

        model = ColQwen2.from_pretrained(MODEL, torch_dtype=torch.bfloat16,
                                         device_map=DEVICE).eval()
        processor = ColQwen2Processor.from_pretrained(MODEL)
        _model = (model, processor)
    return _model


class ImageRequest(BaseModel):
    image_b64: str


class QueryRequest(BaseModel):
    query: str


def _stub_multivector(seed: bytes, n_patches: int) -> list[list[float]]:
    """Deterministic, image-dependent, L2-normalized multivector (no meaning)."""
    import math

    vectors: list[list[float]] = []
    for p in range(n_patches):
        h = hashlib.sha256(seed + p.to_bytes(2, "big")).digest()
        # Expand the 32-byte digest to DIM floats in [-1, 1].
        raw = [((h[i % 32] << 8 | h[(i * 7 + 3) % 32]) / 32767.5) - 1.0
               for i in range(DIM)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        vectors.append([x / norm for x in raw])
    return vectors


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "colqwen", "model": MODEL,
            "device": DEVICE, "implemented": IMPLEMENTED, "dim": DIM}


@app.post("/embed_image")
async def embed_image(req: ImageRequest) -> dict:
    try:
        png = base64.b64decode(req.image_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid image_b64: {exc}") from exc
    if not png:
        raise HTTPException(status_code=400, detail="empty image")

    if not IMPLEMENTED:
        return {"multivector": _stub_multivector(png, STUB_PATCHES),
                "model": MODEL, "stub": True}

    # pragma: no cover - GPU-host path
    from io import BytesIO

    import torch
    from PIL import Image

    model, processor = _load_model()
    image = Image.open(BytesIO(png)).convert("RGB")
    batch = processor.process_images([image]).to(DEVICE)
    with torch.no_grad():
        emb = model(**batch)
    return {"multivector": emb[0].float().cpu().tolist(), "model": MODEL, "stub": False}


@app.post("/embed_query")
async def embed_query(req: QueryRequest) -> dict:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="empty query")
    if not IMPLEMENTED:
        return {"multivector": _stub_multivector(req.query.encode("utf-8"), 8),
                "model": MODEL, "stub": True}

    # pragma: no cover - GPU-host path
    import torch

    model, processor = _load_model()
    batch = processor.process_queries([req.query]).to(DEVICE)
    with torch.no_grad():
        emb = model(**batch)
    return {"multivector": emb[0].float().cpu().tolist(), "model": MODEL, "stub": False}
