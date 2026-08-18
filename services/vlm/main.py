"""VLM HTTP service — figure captioning (Phase 2).

Runs Qwen2.5-VL-7B (CPU at ingest, off-peak batch per ADR 0.3) to caption
cropped figures for retrieval. Called only by the worker during ingestion,
never on the query path.

Backends (`VLM_BACKEND`):
- `stub` (default, dev/CPU): a deterministic, clearly-labelled placeholder
  ("[STUB-Caption]") so the ingestion pipeline is exercised without a model.
- `transformers` (prod GPU host): loads the HF model (Qwen2.5-VL) in-process.
- `openai`: captions via any OpenAI-compatible vision endpoint (e.g. a local
  Ollama vision model at http://ollama:11434/v1). Lets a quantized VL model run
  on a CPU host — the practical "real captions without a GPU" path.
For backward compatibility, `VLM_IMPLEMENTED=true` (with no explicit backend)
selects `transformers`.

Contract (`POST /caption`): `{image_b64, kind, page}` -> `{caption, model, stub}`.
`/summarize` is kept as a backward-compatible alias.
"""

from __future__ import annotations

import base64
import hashlib
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
DEVICE = os.environ.get("VLM_DEVICE", "cpu")
IMPLEMENTED = os.environ.get("VLM_IMPLEMENTED", "false").lower() == "true"
# stub | transformers | openai. Default keeps back-compat with VLM_IMPLEMENTED.
BACKEND = os.environ.get("VLM_BACKEND", "transformers" if IMPLEMENTED else "stub").lower()
# openai backend (e.g. local Ollama vision model, OpenAI-compatible):
VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "http://ollama:11434/v1")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "not-needed-local")
VLM_TIMEOUT_S = int(os.environ.get("VLM_TIMEOUT_S", "180"))

# Fixed DE/EN extraction prompt — kept in sync with app/ingestion/figures.py.
CAPTION_PROMPT = (
    "Beschreibe die Abbildung faktisch auf Deutsch: Art und Inhalt, "
    "Achsenbeschriftungen und Legenden mit konkret abgelesenen Werten, "
    "sämtlichen sichtbaren Text (OCR) und erkennbare Trends. Englischen Text "
    "im Original übernehmen. Keine Spekulation über nicht Sichtbares."
)

app = FastAPI(title="VLM (figure captioning)", version="0.2.0")

_model = None


def _load_model():  # pragma: no cover - GPU-host only
    global _model
    if _model is None:
        from transformers import AutoModelForVision2Seq, AutoProcessor

        processor = AutoProcessor.from_pretrained(MODEL)
        model = AutoModelForVision2Seq.from_pretrained(MODEL, device_map=DEVICE)
        _model = (processor, model)
    return _model


class CaptionRequest(BaseModel):
    image_b64: str
    kind: str = "figure"  # figure | chart | diagram | image | table
    page: int | None = None


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "vlm",
        "model": MODEL,
        "device": DEVICE,
        "backend": BACKEND,
        "implemented": IMPLEMENTED,
    }


def _caption_openai(png: bytes) -> str:
    """Caption via an OpenAI-compatible vision endpoint (e.g. local Ollama).
    Sends the image as a data-URL content part with the DE/EN extraction prompt."""
    import httpx

    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    resp = httpx.post(
        f"{VLM_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {VLM_API_KEY}"},
        json={
            "model": MODEL,
            "temperature": 0,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": CAPTION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
        },
        timeout=VLM_TIMEOUT_S,
    )
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


def _stub_caption(png: bytes, kind: str, page: int | None) -> str:
    """Deterministic, clearly-labelled placeholder (no GPU needed)."""
    digest = hashlib.sha256(png).hexdigest()[:8]
    where = f" auf Seite {page}" if page is not None else ""
    return (f"[STUB-Caption] Abbildung ({kind}){where}, {len(png)} Bytes, "
            f"Prüfsumme {digest}. Echte VLM-Beschreibung erfolgt auf dem "
            f"GPU-Host (VLM_IMPLEMENTED=true).")


@app.post("/caption")
async def caption(req: CaptionRequest) -> dict:
    try:
        png = base64.b64decode(req.image_b64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid image_b64: {exc}") from exc
    if not png:
        raise HTTPException(status_code=400, detail="empty image")

    if BACKEND == "stub":
        return {"caption": _stub_caption(png, req.kind, req.page),
                "model": MODEL, "stub": True}

    if BACKEND == "openai":
        try:
            return {"caption": _caption_openai(png), "model": MODEL, "stub": False}
        except Exception as exc:  # noqa: BLE001 - surface a clear 502 to the worker
            raise HTTPException(status_code=502,
                                detail=f"VLM openai backend failed: {exc}") from exc

    # BACKEND == "transformers" — pragma: no cover - GPU-host path
    from io import BytesIO

    from PIL import Image

    processor, model = _load_model()
    image = Image.open(BytesIO(png)).convert("RGB")
    messages = [{"role": "user", "content": [
        {"type": "image", "image": image},
        {"type": "text", "text": CAPTION_PROMPT},
    ]}]
    prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
    inputs = processor(text=[prompt], images=[image], return_tensors="pt").to(DEVICE)
    out = model.generate(**inputs, max_new_tokens=400, do_sample=False)
    text = processor.batch_decode(out, skip_special_tokens=True)[0].strip()
    return {"caption": text, "model": MODEL, "stub": False}


@app.post("/summarize")
async def summarize(req: CaptionRequest) -> dict:
    """Backward-compatible alias for /caption."""
    return await caption(req)
