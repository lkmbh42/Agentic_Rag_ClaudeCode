"""Ingestion DoD (part 2): dedup on re-upload, and delete removes all vectors.

Indexing is exercised synchronously (the indexer the worker runs), so the test
does not depend on a live worker process.
"""

from __future__ import annotations

import os
import uuid

from app.ingestion import storage
from app.ingestion.embedder import HashingEmbedder
from app.ingestion.indexer import index_document
from app.models.chunk import DocumentChunk
from app.models.collection import Collection
from app.models.department import Department
from app.models.document import Document
from app.models.enums import DocumentStatus


def _make_document(db, filename: str, data: bytes) -> Document:
    dept = Department(name=f"D-{uuid.uuid4().hex[:8]}")
    db.add(dept)
    db.flush()
    coll = Collection(name=f"C-{uuid.uuid4().hex[:8]}", department_id=dept.id)
    db.add(coll)
    db.flush()
    doc = Document(
        collection_id=coll.id, filename=filename, file_type="pdf",
        content_hash=uuid.uuid4().hex, status=DocumentStatus.PENDING,
    )
    db.add(doc)
    db.flush()
    storage.save_document(doc.id, filename, data)
    db.commit()
    return doc


def test_index_persists_chunks_and_vectors(sync_session, test_qindex, samples_dir):
    with open(os.path.join(samples_dir, "normal.pdf"), "rb") as fh:
        data = fh.read()
    doc = _make_document(sync_session, "normal.pdf", data)

    count = index_document(sync_session, doc.id, embedder=HashingEmbedder(), qindex=test_qindex)
    assert count > 0

    chunks = sync_session.query(DocumentChunk).filter_by(document_id=doc.id).all()
    assert len(chunks) == count
    # ACL metadata is denormalized onto every chunk.
    assert all(c.collection_id == doc.collection_id for c in chunks)
    # Vectors landed in Qdrant.
    assert test_qindex.count_for_document(doc.id) == count

    refreshed = sync_session.get(Document, doc.id)
    assert refreshed.status == DocumentStatus.INDEXED


def test_reindex_is_idempotent(sync_session, test_qindex, samples_dir):
    with open(os.path.join(samples_dir, "sample.docx"), "rb") as fh:
        data = fh.read()
    doc = _make_document(sync_session, "sample.docx", data)
    doc.file_type = "docx"
    sync_session.commit()

    first = index_document(sync_session, doc.id, qindex=test_qindex)
    second = index_document(sync_session, doc.id, qindex=test_qindex)
    assert first == second
    # No duplicate points after re-index.
    assert test_qindex.count_for_document(doc.id) == second


def test_delete_removes_all_vectors(sync_session, test_qindex, samples_dir):
    with open(os.path.join(samples_dir, "normal.pdf"), "rb") as fh:
        data = fh.read()
    doc = _make_document(sync_session, "normal.pdf", data)
    doc_id = doc.id

    count = index_document(sync_session, doc_id, qindex=test_qindex)
    assert count > 0 and test_qindex.count_for_document(doc_id) > 0

    # Delete cascade: Qdrant points, then Postgres row (chunks cascade).
    test_qindex.delete_by_document(doc_id)
    sync_session.delete(sync_session.get(Document, doc_id))
    sync_session.commit()

    assert test_qindex.count_for_document(doc_id) == 0
    assert sync_session.query(DocumentChunk).filter_by(document_id=doc_id).count() == 0


# ---- dedup + ACL via the async API -----------------------------------------
async def test_upload_dedup(client, seed, login):
    headers = await login(seed["admin"]["email"], seed["admin"]["password"])
    payload = b"name,role\nAlice,Engineer\n"
    files = {"file": ("people.csv", payload, "text/csv")}
    form = {"collection_id": str(seed["coll_a"])}

    r1 = await client.post("/documents/upload", headers=headers, data=form, files=files)
    assert r1.status_code == 201, r1.text
    assert r1.json()["duplicate"] is False

    r2 = await client.post(
        "/documents/upload", headers=headers, data=form,
        files={"file": ("people.csv", payload, "text/csv")},
    )
    assert r2.status_code == 201
    assert r2.json()["duplicate"] is True  # same content hash

    listing = await client.get(f"/documents?collection_id={seed['coll_a']}", headers=headers)
    assert len(listing.json()) == 1  # not double-indexed


async def test_upload_denied_cross_department(client, seed, login):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    r = await client.post(
        "/documents/upload", headers=alice,
        data={"collection_id": str(seed["coll_b"])},
        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert r.status_code == 404  # alice can't see Finance's collection
