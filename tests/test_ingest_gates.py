"""Phase 2 DoD gate tests (automated, CI):
- re-ingesting an unchanged document creates ZERO new vectors (idempotency);
- 100 % of new objects (text chunks + page images) carry the ACL payload.

Exercises the real Docling pipeline end-to-end, so marked `docling` (slow).
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.ingestion import storage
from app.ingestion.acl_audit import REQUIRED_ACL_KEYS, audit_collection
from app.ingestion.indexer import index_document
from app.models.collection import Collection
from app.models.department import Department
from app.models.document import Document
from app.models.enums import DocumentStatus

pytestmark = pytest.mark.docling


@pytest.fixture
def seeded_pdf(sync_session):
    dept = Department(name=f"D-{uuid.uuid4().hex[:6]}")
    sync_session.add(dept)
    sync_session.flush()
    coll = Collection(name=f"C-{uuid.uuid4().hex[:6]}", department_id=dept.id)
    sync_session.add(coll)
    sync_session.flush()
    doc = Document(collection_id=coll.id, filename="table.pdf", file_type="pdf",
                   content_hash=uuid.uuid4().hex, status=DocumentStatus.PENDING)
    sync_session.add(doc)
    sync_session.commit()
    return doc


def _count(qindex, document_id) -> int:
    return qindex.count_for_document(document_id)


def test_reingest_creates_zero_new_vectors(sync_session, test_qindex,
                                           samples_dir, seeded_pdf, monkeypatch):
    with open(os.path.join(samples_dir, "table.pdf"), "rb") as fh:
        data = fh.read()
    monkeypatch.setattr(storage, "read_document", lambda _i, _n: data)

    index_document(sync_session, seeded_pdf.id, qindex=test_qindex)
    first = _count(test_qindex, seeded_pdf.id)
    assert first > 0

    # Re-ingest the identical document — idempotent clear-then-write.
    index_document(sync_session, seeded_pdf.id, qindex=test_qindex)
    second = _count(test_qindex, seeded_pdf.id)
    assert second == first, f"re-ingest changed vector count {first} -> {second}"

    # And the persisted chunk rows must not have doubled either.
    from app.models.chunk import DocumentChunk

    rows = sync_session.query(DocumentChunk).filter_by(document_id=seeded_pdf.id).count()
    assert rows == first


def test_all_indexed_objects_carry_acl_payload(sync_session, test_qindex,
                                               samples_dir, seeded_pdf, monkeypatch):
    with open(os.path.join(samples_dir, "chart.pdf"), "rb") as fh:
        data = fh.read()
    monkeypatch.setattr(storage, "read_document", lambda _i, _n: data)

    index_document(sync_session, seeded_pdf.id, qindex=test_qindex)

    violations = audit_collection(test_qindex.client, test_qindex.collection)
    assert violations == [], f"objects missing ACL payload: {violations}"

    # Positive check: every point really has both keys, non-empty.
    points, _ = test_qindex.client.scroll(test_qindex.collection, limit=256,
                                          with_payload=True)
    assert points
    for p in points:
        for key in REQUIRED_ACL_KEYS:
            assert (p.payload or {}).get(key), f"point {p.id} missing {key}"
