"""Phase 2 figure pipeline: VLM /caption service (stub), captioner client with
graceful fallback, and the end-to-end indexer sink (crop → MinIO → image_uri,
PNG stripped from payloads).
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest

from app.ingestion import figures as figures_mod
from app.ingestion.figures import FigureCaptioner
from app.models.enums import ChunkType

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


# --------------------------------------------------------------- vlm service
def test_vlm_caption_stub_is_deterministic_and_labelled():
    from fastapi.testclient import TestClient

    from services.vlm.main import app

    c = TestClient(app)
    body = {"image_b64": base64.b64encode(PNG_1PX).decode(), "kind": "chart", "page": 4}
    r1 = c.post("/caption", json=body)
    r2 = c.post("/caption", json=body)
    assert r1.status_code == 200
    assert r1.json()["stub"] is True
    assert r1.json()["caption"] == r2.json()["caption"]  # deterministic
    assert "[STUB-Caption]" in r1.json()["caption"]
    assert "Seite 4" in r1.json()["caption"] and "chart" in r1.json()["caption"]


def test_vlm_caption_rejects_bad_input():
    from fastapi.testclient import TestClient

    from services.vlm.main import app

    c = TestClient(app)
    assert c.post("/caption", json={"image_b64": "!!!not-base64!!!"}).status_code == 400
    assert c.post("/caption", json={"image_b64": ""}).status_code == 400


def test_vlm_summarize_is_caption_alias():
    from fastapi.testclient import TestClient

    from services.vlm.main import app

    c = TestClient(app)
    r = c.post("/summarize", json={"image_b64": base64.b64encode(PNG_1PX).decode()})
    assert r.status_code == 200 and r.json()["stub"] is True


# ------------------------------------------------------------- captioner client
def test_captioner_disabled_returns_fallback(monkeypatch):
    monkeypatch.setattr(figures_mod._settings, "visual_path", "degraded")
    cap = FigureCaptioner()
    assert cap.enabled is False
    assert cap.caption(PNG_1PX, fallback="Originalbildunterschrift") == "Originalbildunterschrift"
    assert cap.caption(PNG_1PX) == "[Abbildung ohne Beschreibung]"


def test_captioner_calls_service_when_full(monkeypatch):
    monkeypatch.setattr(figures_mod._settings, "visual_path", "full")
    monkeypatch.setattr(figures_mod._settings, "vlm_base_url", "http://vlm:8002")
    cap = FigureCaptioner()
    assert cap.enabled is True

    sent = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self): ...

        def json(self):
            return {"caption": "Balkendiagramm: Umsatz steigt von 10 auf 40."}

    def _post(url, json, timeout):
        sent["url"] = url
        sent["kind"] = json["kind"]
        return _Resp()

    monkeypatch.setattr(figures_mod.httpx, "post", _post)
    out = cap.caption(PNG_1PX, kind="chart", page=2, fallback="fb")
    assert out == "Balkendiagramm: Umsatz steigt von 10 auf 40."
    assert sent["url"] == "http://vlm:8002/caption" and sent["kind"] == "chart"


def test_captioner_service_error_falls_back(monkeypatch):
    monkeypatch.setattr(figures_mod._settings, "visual_path", "full")
    monkeypatch.setattr(figures_mod._settings, "vlm_base_url", "http://vlm:8002")

    def _boom(*a, **kw):
        raise figures_mod.httpx.ConnectError("refused")

    monkeypatch.setattr(figures_mod.httpx, "post", _boom)
    cap = FigureCaptioner()
    assert cap.caption(PNG_1PX, fallback="Fallback-Text") == "Fallback-Text"


# --------------------------------------------------------- indexer integration
@pytest.mark.docling
def test_index_document_uploads_figure_and_strips_bytes(
    sync_session, test_qindex, samples_dir, monkeypatch
):
    """chart.pdf through index_document: the embedded figure is cropped to
    MinIO, the chunk carries image_uri, and no PNG bytes leak into Postgres or
    Qdrant payloads. Runs with the dev degraded path (fallback caption)."""
    from app.ingestion import storage
    from app.ingestion.indexer import index_document
    from app.ingestion.object_store import get_object_store, parse_uri
    from app.models.chunk import DocumentChunk
    from app.models.collection import Collection
    from app.models.department import Department
    from app.models.document import Document
    from app.models.enums import DocumentStatus

    dept = Department(name=f"D-{uuid.uuid4().hex[:6]}")
    sync_session.add(dept)
    sync_session.flush()
    coll = Collection(name=f"C-{uuid.uuid4().hex[:6]}", department_id=dept.id)
    sync_session.add(coll)
    sync_session.flush()
    doc = Document(collection_id=coll.id, filename="chart.pdf", file_type="pdf",
                   content_hash=uuid.uuid4().hex, status=DocumentStatus.PENDING)
    sync_session.add(doc)
    sync_session.commit()

    with open(os.path.join(samples_dir, "chart.pdf"), "rb") as fh:
        data = fh.read()
    monkeypatch.setattr(storage, "read_document", lambda _id, _name: data)

    stages: list[str] = []
    index_document(sync_session, doc.id, qindex=test_qindex,
                   on_stage=stages.append)

    assert "captioning" in stages  # figure present → CAPTIONING fired
    figs = [c for c in sync_session.query(DocumentChunk)
            .filter_by(document_id=doc.id, chunk_type=ChunkType.IMAGE).all()]
    assert figs, "no figure chunk persisted"
    uri = (figs[0].source_metadata or {}).get("image_uri")
    assert uri and uri.startswith("s3://figures/")
    # No binary blob in the persisted metadata.
    assert "image_png" not in (figs[0].source_metadata or {})

    # The object really exists in MinIO and is a PNG.
    png = get_object_store().get(uri)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    get_object_store().delete_document(doc.id)
