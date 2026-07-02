"""Semantic-cache DoD: a cache entry is never served cross-scope; TTL and
invalidation evict correctly."""

from __future__ import annotations

import uuid

import pytest
from qdrant_client import models

from app.retrieval.semantic_cache import SemanticCache


@pytest.fixture
def cache():
    sc = SemanticCache(collection=f"semcache_test_{uuid.uuid4().hex[:8]}")
    sc.ensure_collection()
    yield sc
    if sc.client.collection_exists(sc.collection):
        sc.client.delete_collection(sc.collection)


def test_hit_within_scope(cache):
    coll = uuid.uuid4()
    doc = uuid.uuid4()
    cache.store("What is the remote work policy?", "Three days per week.", {coll}, {doc})

    hit = cache.lookup({coll}, "What is the remote work policy?")
    assert hit is not None
    assert hit.answer == "Three days per week."


def test_never_served_cross_scope(cache):
    coll_a = uuid.uuid4()
    coll_b = uuid.uuid4()
    cache.store("Remote work policy?", "From collection A.", {coll_a}, {uuid.uuid4()})

    # A user who cannot access coll_a must NOT get the cached answer.
    assert cache.lookup({coll_b}, "Remote work policy?") is None
    # A user with a superset of the scope may.
    assert cache.lookup({coll_a, coll_b}, "Remote work policy?") is not None


def test_stale_entry_not_served(cache):
    coll = uuid.uuid4()
    entry_id = cache.store("Stale question?", "old answer", {coll}, set())
    # Force the entry to look ancient.
    cache.client.set_payload(
        cache.collection, payload={"created_at": 0.0},
        points=[str(entry_id)], wait=True,
    )
    assert cache.lookup({coll}, "Stale question?") is None


def test_invalidate_collection_evicts(cache):
    coll = uuid.uuid4()
    cache.store("Q for coll?", "answer", {coll}, set())
    assert cache.lookup({coll}, "Q for coll?") is not None

    removed = cache.invalidate_collection(coll)
    assert removed == 1
    assert cache.lookup({coll}, "Q for coll?") is None


def test_invalidate_document_evicts(cache):
    coll = uuid.uuid4()
    doc = uuid.uuid4()
    cache.store("Q for doc?", "answer", {coll}, {doc})
    assert cache.lookup({coll}, "Q for doc?") is not None

    removed = cache.invalidate_document(doc)
    assert removed == 1
    assert cache.lookup({coll}, "Q for doc?") is None
