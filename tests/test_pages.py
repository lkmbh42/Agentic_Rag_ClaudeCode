"""Phase 2 page-image pipeline: render ≤1024px, ColQwen2 service (stub),
docs_pages multivector collection (MAX_SIM + binary quantization + ACL payload),
and idempotent index_pages.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest

from app.ingestion import pages as pages_mod
from app.ingestion.pages import ColQwenClient, RenderedPage, index_pages, render_pages
from app.ingestion.pages_index import PagesIndex, page_payload


# ------------------------------------------------------------- render (CPU)
def test_render_pages_bounds_longest_edge(samples_dir):
    from PIL import Image
    import io

    with open(os.path.join(samples_dir, "normal.pdf"), "rb") as fh:
        pdf = fh.read()
    rendered = render_pages(pdf, max_px=1024)
    assert rendered and all(isinstance(p, RenderedPage) for p in rendered)
    assert [p.page_number for p in rendered] == list(range(1, len(rendered) + 1))
    for p in rendered:
        assert p.png[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = Image.open(io.BytesIO(p.png)).size
        assert max(w, h) <= 1024


# ------------------------------------------------------------- colqwen service
def test_colqwen_stub_multivector_shape_and_determinism():
    from fastapi.testclient import TestClient

    from services.colqwen.main import DIM, app

    c = TestClient(app)
    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"payload").decode()
    r1 = c.post("/embed_image", json={"image_b64": png_b64})
    r2 = c.post("/embed_image", json={"image_b64": png_b64})
    assert r1.status_code == 200 and r1.json()["stub"] is True
    mv = r1.json()["multivector"]
    assert isinstance(mv, list) and all(len(v) == DIM for v in mv)
    assert mv == r2.json()["multivector"]  # deterministic
    # L2-normalized patches.
    for v in mv:
        assert abs(sum(x * x for x in v) - 1.0) < 1e-6


def test_colqwen_query_and_bad_input():
    from fastapi.testclient import TestClient

    from services.colqwen.main import app

    c = TestClient(app)
    assert c.post("/embed_query", json={"query": "Umsatz 2023"}).json()["stub"] is True
    assert c.post("/embed_query", json={"query": "  "}).status_code == 400
    assert c.post("/embed_image", json={"image_b64": "!!!"}).status_code == 400


# ------------------------------------------------------- docs_pages collection
@pytest.fixture
def pages_index():
    idx = PagesIndex(collection="docs_pages_test")
    if idx.client.collection_exists(idx.collection):
        idx.client.delete_collection(idx.collection)
    idx.ensure_collection()
    yield idx
    if idx.client.collection_exists(idx.collection):
        idx.client.delete_collection(idx.collection)


def test_docs_pages_is_multivector_maxsim_binary_quantized(pages_index):
    info = pages_index.client.get_collection(pages_index.collection)
    vec = info.config.params.vectors["pages"]
    assert vec.multivector_config is not None
    assert vec.multivector_config.comparator.value == "max_sim"
    # Binary quantization active (spec DoD) — configured per named vector.
    assert vec.quantization_config is not None
    assert type(vec.quantization_config).__name__.startswith("Binary")


def test_page_payload_has_text_acl_schema():
    p = page_payload(document_id=uuid.uuid4(), collection_id=uuid.uuid4(),
                     page_number=2, image_uri="s3://pages/x/2.png",
                     file_name="d.pdf", file_type="pdf")
    # Same ACL keys the text schema uses.
    assert "collection_id" in p and "document_id" in p
    assert p["modality"] == "page_image" and p["page_number"] == 2


# ------------------------------------------------------- index_pages (stubbed)
class _StubColQwen:
    enabled = True

    def embed_page(self, png: bytes) -> list[list[float]]:
        return [[0.1] * 128, [0.2] * 128]


def test_index_pages_disabled_returns_zero(monkeypatch):
    monkeypatch.setattr(pages_mod._settings, "visual_path", "degraded")
    from app.ingestion.object_store import ObjectStore

    n = index_pages(uuid.uuid4(), uuid.uuid4(), pdf_bytes=b"",
                    file_name="x.pdf", file_type="pdf",
                    store=ObjectStore(), pages_index=None,
                    colqwen=ColQwenClient())
    assert n == 0


def test_index_pages_full_path_indexes_and_is_idempotent(samples_dir, pages_index):
    from app.ingestion.object_store import ObjectStore

    store = ObjectStore()
    store.ensure_buckets()
    doc_id, coll_id = uuid.uuid4(), uuid.uuid4()
    with open(os.path.join(samples_dir, "normal.pdf"), "rb") as fh:
        pdf = fh.read()

    n1 = index_pages(doc_id, coll_id, pdf_bytes=pdf, file_name="normal.pdf",
                     file_type="pdf", store=store, pages_index=pages_index,
                     colqwen=_StubColQwen())
    assert n1 >= 1
    assert pages_index.count_for_document(doc_id) == n1

    # Re-index: idempotent — same count, no accumulation.
    n2 = index_pages(doc_id, coll_id, pdf_bytes=pdf, file_name="normal.pdf",
                     file_type="pdf", store=store, pages_index=pages_index,
                     colqwen=_StubColQwen())
    assert n2 == n1
    assert pages_index.count_for_document(doc_id) == n1

    store.delete_document(doc_id)
