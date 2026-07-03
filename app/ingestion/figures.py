"""Figure pipeline (Phase 2, spec module `ingest/figures.py`).

For each figure element Docling produced (cropped PNG in metadata):
1. upload the PNG to MinIO (`figures/{doc_id}/{figure_id}.png`) — done by the
   `figure_sink` the indexer wires to `ObjectStore.put_figure`;
2. caption it via the `vlm` service `POST /caption` (Qwen2.5-VL-7B, fixed
   German/English prompt extracting description, axis/legend values, visible
   text/OCR, and stated trends). This reuses the existing worker→VLM service
   boundary (CLAUDE.md §10: the 501 stub is superseded by the captioner);
3. the caption becomes the `type=figure` chunk's content, with `image_uri` in
   its payload.

Hardware reality (Rule 2 / air-gap): the `vlm` service is local. In dev it runs
a deterministic STUB (no GPU); on the prod GPU host `VLM_IMPLEMENTED=true` runs
the real model. When the service is unreachable or errors, captioning degrades
to the document's own caption text (or a neutral placeholder) so ingestion
still completes and figures remain retrievable by surrounding text.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache

import httpx

from app.config import get_settings

logger = logging.getLogger("rag.ingestion.figures")
_settings = get_settings()


class FigureCaptioner:
    """Client for the `vlm` service `/caption` endpoint."""

    def __init__(self) -> None:
        self.base_url = _settings.vlm_base_url.rstrip("/")
        self.enabled = _settings.visual_path == "full" and bool(self.base_url)

    def caption(self, png: bytes, *, kind: str = "figure",
                page: int | None = None, fallback: str | None = None) -> str:
        """Return a retrieval-useful caption. On any failure (or when the visual
        path is degraded) fall back to the provided text or a neutral
        placeholder — never raise, so one bad figure cannot fail the document."""
        if not self.enabled:
            return fallback or "[Abbildung ohne Beschreibung]"
        try:
            resp = httpx.post(
                f"{self.base_url}/caption",
                json={"image_b64": base64.b64encode(png).decode("ascii"),
                      "kind": kind, "page": page},
                timeout=_settings.captioner_timeout_s,
            )
            resp.raise_for_status()
            text = (resp.json().get("caption") or "").strip()
            return text or (fallback or "[Abbildung ohne Beschreibung]")
        except Exception as exc:  # noqa: BLE001 - captioning must never fail a doc
            logger.warning("figure caption failed, using fallback: %s", exc)
            return fallback or "[Abbildung ohne Beschreibung]"


@lru_cache
def get_captioner() -> FigureCaptioner:
    return FigureCaptioner()
