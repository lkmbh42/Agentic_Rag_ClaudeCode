"""Phase 4 DoD security test: image URLs are unreachable without a valid JWT
and the document's collection in the caller's ACL scope. Runs against the real
MinIO on the compose network (same as test_object_store)."""

from __future__ import annotations

import uuid

import pytest

from app.ingestion.object_store import ObjectStore
from app.models.document import Document
from app.models.enums import DocumentStatus

PNG = b"\x89PNG\r\n\x1a\nfake-png-bytes"


@pytest.fixture
def page_doc(seed, sync_session):
    """A document in coll_a (alice's scope) with one page image in MinIO."""
    doc = Document(collection_id=seed["coll_a"], filename="report.pdf",
                   file_type="pdf", content_hash=uuid.uuid4().hex,
                   status=DocumentStatus.INDEXED, page_count=1)
    sync_session.add(doc)
    sync_session.commit()
    store = ObjectStore()
    store.ensure_buckets()
    store.put_page(doc.id, 1, PNG)
    store.put_figure(doc.id, "fig-0001", PNG)
    yield doc
    store.delete_document(doc.id)


async def test_no_jwt_is_rejected(client, page_doc):
    r = await client.get(f"/media/pages/{page_doc.id}/1")
    assert r.status_code == 401


async def test_cross_scope_user_gets_404(client, login, seed, page_doc):
    bob = await login(seed["bob"]["email"], seed["bob"]["password"])
    r = await client.get(f"/media/pages/{page_doc.id}/1", headers=bob)
    assert r.status_code == 404
    r = await client.get(f"/media/figures/{page_doc.id}/fig-0001", headers=bob)
    assert r.status_code == 404


async def test_authorized_user_gets_the_image(client, login, seed, page_doc):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    r = await client.get(f"/media/pages/{page_doc.id}/1", headers=alice)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "private" in r.headers.get("cache-control", "")
    assert r.content == PNG

    r = await client.get(f"/media/figures/{page_doc.id}/fig-0001", headers=alice)
    assert r.status_code == 200
    assert r.content == PNG


async def test_missing_object_and_probes_are_404(client, login, seed, page_doc):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    # page that was never rendered
    r = await client.get(f"/media/pages/{page_doc.id}/99", headers=alice)
    assert r.status_code == 404
    # malformed figure id (traversal/probe shapes)
    r = await client.get(f"/media/figures/{page_doc.id}/..%2Fescape", headers=alice)
    assert r.status_code == 404
    # unknown document id
    r = await client.get(f"/media/pages/{uuid.uuid4()}/1", headers=alice)
    assert r.status_code == 404
