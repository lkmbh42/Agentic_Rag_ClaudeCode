"""Semantic-cache DoD: a cache entry is never served across differing ACL
scopes (Phase 3: scope-hash cache key, strict equality); TTL and invalidation
evict correctly; expired entries are actually deleted (AUDIT §11)."""

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
    # Phase 3 (scope-hash key): even a SUPERSET scope is a different cache key
    # — no sharing across differing permission sets, period. (Pre-Phase-3 the
    # subset rule allowed this; the spec's DoD test is stricter.)
    assert cache.lookup({coll_a, coll_b}, "Remote work policy?") is None
    # The identical scope hits.
    assert cache.lookup({coll_a}, "Remote work policy?") is not None


def test_scope_hash_is_the_cache_key(cache):
    """Explicit Phase 3 DoD test: same question, two users with differing ACL
    scopes — each sees only an answer written under their exact scope."""
    coll_a, coll_b = uuid.uuid4(), uuid.uuid4()
    doc = uuid.uuid4()
    # Alice (scope {a}) asks; answer cached under her scope.
    cache.store("Wie viele Urlaubstage?", "30 Tage (Team A).", {coll_a}, {doc},
                requester_scope={coll_a})
    # Bob (scope {b}) — same question, different permissions: MISS.
    assert cache.lookup({coll_b}, "Wie viele Urlaubstage?") is None
    # Admin (scope {a,b}) — still a different key: MISS, answered fresh.
    assert cache.lookup({coll_a, coll_b}, "Wie viele Urlaubstage?") is None
    # Alice again: HIT.
    hit = cache.lookup({coll_a}, "Wie viele Urlaubstage?")
    assert hit is not None and hit.answer == "30 Tage (Team A)."


def test_stale_entry_not_served_and_opportunistically_evicted(cache):
    coll = uuid.uuid4()
    entry_id = cache.store("Stale question?", "old answer", {coll}, set())
    # Force the entry to look ancient.
    cache.client.set_payload(
        cache.collection, payload={"created_at": 0.0},
        points=[str(entry_id)], wait=True,
    )
    assert cache.lookup({coll}, "Stale question?") is None
    # The lookup that saw the stale entry also deleted it (async delete —
    # give Qdrant a beat).
    import time as _t

    for _ in range(20):
        if cache.client.count(cache.collection, exact=True).count == 0:
            break
        _t.sleep(0.1)
    assert cache.client.count(cache.collection, exact=True).count == 0


def test_purge_expired_sweeps_old_entries(cache):
    coll = uuid.uuid4()
    old = cache.store("Old?", "old", {coll}, set())
    cache.store("Fresh?", "fresh", {coll}, set())
    cache.client.set_payload(
        cache.collection, payload={"created_at": 0.0}, points=[str(old)], wait=True)

    assert cache.purge_expired() == 1
    assert cache.client.count(cache.collection, exact=True).count == 1
    assert cache.lookup({coll}, "Fresh?") is not None


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
