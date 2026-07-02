"""Retrieval DoD: ACL-filtered hybrid retrieval returns only permitted chunks,
and p95 latency on the seed set is within target."""

from __future__ import annotations

import time
import uuid

from app.ingestion import storage
from app.ingestion.indexer import index_document
from app.models.collection import Collection
from app.models.department import Department
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.retrieval.rerank import LexicalReranker
from app.retrieval.retriever import Retriever


def _collection(db, name: str) -> Collection:
    dept = Department(name=f"D-{uuid.uuid4().hex[:8]}")
    db.add(dept)
    db.flush()
    coll = Collection(name=name, department_id=dept.id)
    db.add(coll)
    db.flush()
    db.commit()
    return coll


def _index_text(db, qindex, collection_id, text: str) -> Document:
    doc = Document(
        collection_id=collection_id, filename="d.txt", file_type="txt",
        content_hash=uuid.uuid4().hex, status=DocumentStatus.PENDING,
    )
    db.add(doc)
    db.flush()
    storage.save_document(doc.id, "d.txt", text.encode())
    db.commit()
    index_document(db, doc.id, qindex=qindex)
    return doc


def _retriever(qindex) -> Retriever:
    return Retriever(collection=qindex.collection, reranker=LexicalReranker())


def test_acl_filter_excludes_other_collections(sync_session, test_qindex):
    coll_a = _collection(sync_session, "Eng")
    coll_b = _collection(sync_session, "Finance")
    _index_text(sync_session, test_qindex, coll_a.id,
                "Remote work policy: employees may work remotely three days per week.")
    _index_text(sync_session, test_qindex, coll_b.id,
                "Remote work policy for finance differs and is confidential.")

    r = _retriever(test_qindex)

    # User permitted only coll_a: results must be coll_a-only, even though the
    # query matches coll_b content too.
    res_a = r.search({coll_a.id}, "remote work policy")
    assert res_a, "expected results for permitted collection"
    assert all(c.collection_id == coll_a.id for c in res_a)

    # User permitted only coll_b: never sees coll_a.
    res_b = r.search({coll_b.id}, "remote work policy")
    assert all(c.collection_id == coll_b.id for c in res_b)

    # No access -> nothing.
    assert r.search(set(), "remote work policy") == []


def test_hybrid_retrieval_finds_relevant_chunk(sync_session, test_qindex):
    coll = _collection(sync_session, "Docs")
    _index_text(sync_session, test_qindex, coll.id,
                "The security policy requires multi-factor authentication for all staff.")
    _index_text(sync_session, test_qindex, coll.id,
                "The cafeteria menu changes every week and includes vegetarian options.")

    r = _retriever(test_qindex)
    res = r.search({coll.id}, "multi-factor authentication security")
    assert res
    assert "authentication" in res[0].content.lower()


def test_retrieval_p95_latency_within_target(sync_session, test_qindex):
    from app.config import get_settings

    coll = _collection(sync_session, "Perf")
    for i in range(5):
        _index_text(sync_session, test_qindex, coll.id,
                    f"Document {i} about remote work, security, and budget topic {i}.")

    r = _retriever(test_qindex)
    latencies = []
    for i in range(20):
        t0 = time.perf_counter()
        r.search({coll.id}, f"remote work security {i}")
        latencies.append((time.perf_counter() - t0) * 1000)

    latencies.sort()
    p95 = latencies[int(0.95 * (len(latencies) - 1))]
    target = get_settings().retrieval_p95_target_ms
    assert p95 < target, f"p95={p95:.1f}ms exceeds target {target}ms"
