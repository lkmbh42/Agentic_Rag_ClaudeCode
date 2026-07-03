"""Page-image pipeline (Phase 2, spec module `ingest/pages.py`).

For each page of a document:
1. render it to PNG at ≤`page_render_max_px` longest edge (PyMuPDF, CPU);
2. upload to MinIO (`pages/{doc_id}/{page_no}.png`);
3. embed with ColQwen2 (multivector) via the `colqwen` service;
4. upsert into the Qdrant `docs_pages` multivector collection with the ACL
   payload identical to the text schema.

Enabled only when `visual_path == "full"` (prod GPU host) — ColQwen2 needs a
GPU. In dev/degraded the whole page pass is skipped (like figure captioning);
`render_pages` itself is CPU-only and unit-tested independently.
"""

from __future__ import annotations

import base64
import io
import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import get_settings
from app.ingestion.object_store import ObjectStore
from app.ingestion.pages_index import PagesIndex, page_payload

logger = logging.getLogger("rag.ingestion.pages")
_settings = get_settings()


@dataclass
class RenderedPage:
    page_number: int
    png: bytes


def render_pages(pdf_bytes: bytes, max_px: int | None = None) -> list[RenderedPage]:
    """Render every page to a PNG whose longest edge is ≤ max_px (CPU)."""
    import fitz  # PyMuPDF

    max_px = max_px or _settings.page_render_max_px
    out: list[RenderedPage] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc, start=1):
            rect = page.rect
            longest = max(rect.width, rect.height) or 1.0
            scale = min(1.0, max_px / longest)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            out.append(RenderedPage(page_number=i, png=pix.tobytes("png")))
    return out


class ColQwenClient:
    """Client for the `colqwen` service: PNG → per-patch multivector."""

    def __init__(self) -> None:
        self.base_url = _settings.colqwen_base_url.rstrip("/")
        self.enabled = _settings.visual_path == "full" and bool(self.base_url)

    def embed_page(self, png: bytes) -> list[list[float]]:
        """Return the multivector for a page image. Raises on failure — the
        page pass is best-effort at the caller (a failed page must not fail the
        whole document, but a failure must be visible in logs)."""
        resp = httpx.post(
            f"{self.base_url}/embed_image",
            json={"image_b64": base64.b64encode(png).decode("ascii")},
            timeout=_settings.colqwen_timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["multivector"]


@lru_cache
def get_colqwen() -> ColQwenClient:
    return ColQwenClient()


def index_pages(document_id: uuid.UUID, collection_id: uuid.UUID, *,
                pdf_bytes: bytes, file_name: str, file_type: str,
                store: ObjectStore, pages_index: PagesIndex,
                colqwen: ColQwenClient | None = None) -> int:
    """Render → MinIO → ColQwen2 → docs_pages. Idempotent: clears the document's
    existing page points + objects first. Returns the number of pages indexed.
    Skipped (returns 0) when the visual path is degraded."""
    colqwen = colqwen or get_colqwen()
    if not colqwen.enabled:
        return 0

    pages_index.ensure_collection()
    pages_index.delete_by_document(document_id)

    points = []
    indexed = 0
    for rp in render_pages(pdf_bytes):
        uri = store.put_page(document_id, rp.page_number, rp.png)
        try:
            multivector = colqwen.embed_page(rp.png)
        except Exception as exc:  # noqa: BLE001 - one bad page must not fail the doc
            logger.warning("colqwen embed failed for %s p%d: %s",
                           document_id, rp.page_number, exc)
            continue
        points.append(pages_index.make_point(
            uuid.uuid4(), multivector,
            page_payload(document_id=document_id, collection_id=collection_id,
                         page_number=rp.page_number, image_uri=uri,
                         file_name=file_name, file_type=file_type),
        ))
        indexed += 1

    pages_index.upsert_pages(points)
    return indexed
