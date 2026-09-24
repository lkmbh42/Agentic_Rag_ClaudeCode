"""Permission-scoped semantic cache (Qdrant-backed).

An entry stores the question embedding, the answer, the SOURCE scope the answer
was derived from (collection_ids + document_ids), and — since Phase 3 — the
REQUESTER's ACL scope hash as the cache key's permission component.

Cross-scope safety (CLAUDE.md Phase 3, closes AUDIT F1/F4): a cached answer is
returned only if
  (a) the requester's ACL scope hash EQUALS the entry's scope hash — enforced
      as a filter inside the Qdrant query, so entries from any other scope are
      never even candidates ("cache key includes the user's ACL scope hash");
  (b) the query is similar enough (>= threshold, configurable);
  (c) the entry is not stale (within TTL); AND
  (d) defense in depth: the requester can access EVERY source collection the
      answer used (entry.collection_ids ⊆ requester's allowed set) — trivially
      true when (a) holds, kept as a second, independent barrier.
Note (a) is deliberately STRICTER than the pre-Phase-3 subset rule: two users
with different permission sets never share cache entries, even when one is a
superset of the other. Hit rate pays for hard scope isolation; same-scope
repeat questions (the common case) still hit.

Staleness: expired entries are deleted opportunistically when a lookup walks
past them, and `purge_expired()` sweeps the whole collection (the worker calls
it periodically — AUDIT §11 deferred eviction, folded in here).

Invalidation: entries are tagged in Redis under cache:coll:<id> / cache:doc:<id>,
so document delete/re-version and permission changes evict exactly the affected
entries (lifecycle requirement).
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field

import redis as sync_redis
from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.retrieval.factory import get_embedder

logger = logging.getLogger("rag.retrieval.semantic_cache")
_settings = get_settings()
DENSE = "dense"


def _scope_hash(collection_ids: set[uuid.UUID] | list[str]) -> str:
    return hashlib.sha256(
        "|".join(sorted(str(c) for c in collection_ids)).encode()
    ).hexdigest()


@dataclass
class CacheHit:
    answer: str
    query_text: str
    score: float
    collection_ids: list[str]
    document_ids: list[str]
    # Full citation records (marker, page, chunk_type, content, image_uri, …) so a
    # cached answer keeps its verifiable sources — the source-preview panel needs
    # these, not just document ids.
    citations: list[dict] = field(default_factory=list)


class SemanticCache:
    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        self.collection = collection or _settings.semantic_cache_collection
        self.client = QdrantClient(url=url or _settings.qdrant_url, timeout=30)
        self.redis = sync_redis.from_url(_settings.redis_url, decode_responses=True)
        self.embedder = get_embedder()

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config={DENSE: models.VectorParams(
                    size=_settings.embedding_dim, distance=models.Distance.COSINE)},
            )
            self.client.create_payload_index(
                self.collection, field_name="scope_hash",
                field_schema=models.PayloadSchemaType.KEYWORD)

    # ---------------------------------------------------------------- lookup
    def lookup(self, allowed_collection_ids: set[uuid.UUID], query: str) -> CacheHit | None:
        if not query.strip() or not self.client.collection_exists(self.collection):
            return None
        allowed = {str(c) for c in allowed_collection_ids}
        dense = self.embedder.embed_dense(query)

        response = self.client.query_points(
            self.collection,
            query=dense,
            using=DENSE,
            # The permission component of the cache key: only entries written
            # under the SAME ACL scope are candidates. Pre-Phase-3 entries have
            # no scope_hash and are therefore never served (safe migration).
            query_filter=models.Filter(must=[models.FieldCondition(
                key="scope_hash",
                match=models.MatchValue(value=_scope_hash(allowed)))]),
            limit=5,
            score_threshold=_settings.semantic_cache_similarity,
            with_payload=True,
        )
        now = time.time()
        stale_ids: list[str] = []
        hit: CacheHit | None = None
        for p in response.points:
            payload = p.payload or {}
            if now - float(payload.get("created_at", 0)) > _settings.semantic_cache_ttl_s:
                stale_ids.append(str(p.id))  # opportunistic eviction below
                continue
            entry_colls = set(payload.get("collection_ids", []))
            if not entry_colls.issubset(allowed):
                continue  # defense in depth — unreachable when scope_hash matched
            if hit is None:
                hit = CacheHit(
                    answer=payload.get("answer", ""),
                    query_text=payload.get("query_text", ""),
                    score=float(p.score),
                    collection_ids=list(entry_colls),
                    document_ids=list(payload.get("document_ids", [])),
                    citations=list(payload.get("citations", [])),
                )
        if stale_ids:
            try:
                self.client.delete(
                    self.collection,
                    points_selector=models.PointIdsList(points=stale_ids), wait=False)
            except Exception as exc:  # noqa: BLE001 - eviction is best-effort
                logger.debug("opportunistic eviction failed: %s", exc)
        return hit

    # ----------------------------------------------------------------- store
    def store(
        self,
        query: str,
        answer: str,
        source_collection_ids: set[uuid.UUID],
        source_document_ids: set[uuid.UUID],
        requester_scope: set[uuid.UUID] | None = None,
        citations: list[dict] | None = None,
    ) -> uuid.UUID:
        """`requester_scope` is the ASKER's full allowed-collection set — the
        permission component of the cache key. Defaults to the source
        collections (narrowest safe scope) when a caller doesn't supply it."""
        self.ensure_collection()
        entry_id = uuid.uuid4()
        coll_ids = [str(c) for c in source_collection_ids]
        doc_ids = [str(d) for d in source_document_ids]
        scope = requester_scope if requester_scope is not None else source_collection_ids
        self.client.upsert(self.collection, points=[models.PointStruct(
            id=str(entry_id),
            vector={DENSE: self.embedder.embed_dense(query)},
            payload={
                "answer": answer,
                "query_text": query,
                "collection_ids": coll_ids,
                "document_ids": doc_ids,
                "citations": citations or [],
                "scope_hash": _scope_hash(scope),
                "created_at": time.time(),
            },
        )], wait=True)
        # Tag for targeted invalidation.
        pipe = self.redis.pipeline()
        for cid in coll_ids:
            pipe.sadd(f"cache:coll:{cid}", str(entry_id))
        for did in doc_ids:
            pipe.sadd(f"cache:doc:{did}", str(entry_id))
        pipe.execute()
        return entry_id

    # ------------------------------------------------------------ invalidate
    def _evict(self, tag_key: str) -> int:
        ids = self.redis.smembers(tag_key)
        if not ids:
            return 0
        self.client.delete(
            self.collection,
            points_selector=models.PointIdsList(points=list(ids)),
            wait=True,
        )
        self.redis.delete(tag_key)
        return len(ids)

    def invalidate_document(self, document_id: uuid.UUID) -> int:
        return self._evict(f"cache:doc:{document_id}")

    def invalidate_collection(self, collection_id: uuid.UUID) -> int:
        return self._evict(f"cache:coll:{collection_id}")

    def purge_expired(self) -> int:
        """Delete every entry past TTL (AUDIT §11 deferred eviction). Cheap:
        a payload-range filter delete; the worker runs it periodically."""
        if not self.client.collection_exists(self.collection):
            return 0
        cutoff = time.time() - _settings.semantic_cache_ttl_s
        flt = models.Filter(must=[models.FieldCondition(
            key="created_at", range=models.Range(lt=cutoff))])
        before = self.client.count(
            self.collection, count_filter=flt, exact=True).count
        if before:
            self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(filter=flt), wait=True)
        return int(before)
