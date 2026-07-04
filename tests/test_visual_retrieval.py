"""Visual page retrieval tests (Phase 3).

Runs against the real Qdrant on the compose network with a throwaway
`docs_pages_test` collection (same isolation idiom as test_qindex). The colqwen
service is faked — dev has no GPU — so these tests prove the QUERY wiring:
MAX_SIM multivector search, the in-query ACL filter (Rule 5), the top-4 cap,
and every degradation path.

Vectors use full-dimension ±1 sign patterns so binary quantization (active on
the collection, Phase 2) preserves their ordering.
"""

from __future__ import annotations

import uuid

import pytest

from app.config import get_settings
from app.ingestion.pages_index import PagesIndex, page_payload
from app.retrieval.visual import VisualRetriever

_settings = get_settings()
DIM = _settings.colqwen_dim


def _sign_vector(bits: int) -> list[float]:
    """Deterministic ±1 pattern (normalized) derived from an int seed."""
    import math

    raw = [1.0 if (bits >> (i % 32)) & 1 else -1.0 for i in range(DIM)]
    norm = math.sqrt(DIM)
    return [x / norm for x in raw]


PLUS = [1.0 / (DIM ** 0.5)] * DIM  # the "query-like" direction
MINUS = [-x for x in PLUS]


class FakeColQwen:
    def __init__(self, mv=None, enabled=True, exc=None):
        self.enabled = enabled
        self._mv, self._exc = mv or [PLUS], exc
        self.calls = 0

    def embed_query(self, query):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._mv


@pytest.fixture
def pages_index_test():
    pi = PagesIndex(collection="docs_pages_test")
    if pi.client.collection_exists(pi.collection):
        pi.client.delete_collection(pi.collection)
    pi.ensure_collection()
    yield pi
    if pi.client.collection_exists(pi.collection):
        pi.client.delete_collection(pi.collection)


def _seed_page(pi: PagesIndex, collection_id: uuid.UUID, document_id: uuid.UUID,
               page_number: int, multivector: list[list[float]]) -> None:
    pi.upsert_pages([pi.make_point(
        uuid.uuid4(), multivector,
        page_payload(document_id=document_id, collection_id=collection_id,
                     page_number=page_number,
                     image_uri=f"s3://pages/{document_id}/{page_number}.png",
                     file_name="doc.pdf", file_type="pdf"),
    )])


def _retriever(pi, colqwen) -> VisualRetriever:
    return VisualRetriever(colqwen=colqwen, collection=pi.collection)


# ------------------------------------------------------------------ ACL gate
def test_acl_filter_excludes_other_collections(pages_index_test):
    coll_a, coll_b = uuid.uuid4(), uuid.uuid4()
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    # Identical (maximally scoring) vectors in BOTH collections: if the filter
    # were post-hoc, the collB page would tie at the top.
    _seed_page(pages_index_test, coll_a, doc_a, 1, [PLUS])
    _seed_page(pages_index_test, coll_b, doc_b, 1, [PLUS])

    hits = _retriever(pages_index_test, FakeColQwen()).search({coll_a}, "chart query")
    assert len(hits) == 1
    assert hits[0].collection_id == coll_a
    assert hits[0].document_id == doc_a


def test_empty_allowed_set_returns_nothing_without_calls(pages_index_test):
    fake = FakeColQwen()
    hits = _retriever(pages_index_test, fake).search(set(), "query")
    assert hits == []
    assert fake.calls == 0


# ------------------------------------------------------------------- ranking
def test_max_sim_orders_pages_and_caps_at_top_k(pages_index_test):
    coll = uuid.uuid4()
    # One clearly-aligned page, one anti-aligned, plus fillers → cap at 4.
    _seed_page(pages_index_test, coll, uuid.uuid4(), 1, [PLUS])
    _seed_page(pages_index_test, coll, uuid.uuid4(), 2, [MINUS])
    for page_no in range(3, 9):
        _seed_page(pages_index_test, coll, uuid.uuid4(), page_no,
                   [_sign_vector(0x9E3779B9 * page_no & 0xFFFFFFFF)])

    hits = _retriever(pages_index_test, FakeColQwen()).search({coll}, "query")
    assert len(hits) == _settings.visual_top_k_pages == 4
    assert hits[0].page_number == 1, "the aligned page must rank first (MAX_SIM)"
    assert all(hits[0].score >= h.score for h in hits)
    assert hits[0].image_uri.startswith("s3://pages/")


# -------------------------------------------------------------- degradation
def test_disabled_visual_path_returns_empty(pages_index_test):
    fake = FakeColQwen(enabled=False)
    hits = _retriever(pages_index_test, fake).search({uuid.uuid4()}, "query")
    assert hits == []
    assert fake.calls == 0


def test_embed_failure_degrades_to_empty(pages_index_test):
    coll = uuid.uuid4()
    _seed_page(pages_index_test, coll, uuid.uuid4(), 1, [PLUS])
    fake = FakeColQwen(exc=RuntimeError("colqwen down"))
    assert _retriever(pages_index_test, fake).search({coll}, "query") == []


def test_missing_collection_returns_empty():
    retriever = VisualRetriever(colqwen=FakeColQwen(),
                                collection="docs_pages_does_not_exist")
    assert retriever.search({uuid.uuid4()}, "query") == []


def test_blank_query_returns_empty(pages_index_test):
    fake = FakeColQwen()
    assert _retriever(pages_index_test, fake).search({uuid.uuid4()}, "  ") == []
    assert fake.calls == 0
