"""Permission-scoped semantic cache (Qdrant-backed).

An entry stores the question embedding, the answer, and the SOURCE scope the
answer was derived from (collection_ids + document_ids) plus a permission_hash.

Cross-scope safety (security requirement): a cached answer is returned only if
  (a) the query is similar enough (>= threshold),
  (b) the entry is not stale (within TTL), AND
  (c) the requester can access EVERY source collection the answer used
      (entry.collection_ids ⊆ requester's allowed set).
Rule (c) is authoritative — a cache entry is never served cross-scope even if a
similar question was asked by a more-privileged user.

Invalidation: entries are tagged in Redis under cache:coll:<id> / cache:doc:<id>,
so document delete/re-version and permission changes evict exactly the affected
entries (lifecycle requirement).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import redis as sync_redis
from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.retrieval.factory import get_embedder

_settings = get_settings()
DENSE = "dense"


def _permission_hash(collection_ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(collection_ids)).encode()).hexdigest()


@dataclass
class CacheHit:
    answer: str
    query_text: str
    score: float
    collection_ids: list[str]
    document_ids: list[str]


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
            limit=5,
            score_threshold=_settings.semantic_cache_similarity,
            with_payload=True,
        )
        now = time.time()
        for p in response.points:
            payload = p.payload or {}
            if now - float(payload.get("created_at", 0)) > _settings.semantic_cache_ttl_s:
                continue  # stale
            entry_colls = set(payload.get("collection_ids", []))
            if not entry_colls.issubset(allowed):
                continue  # cross-scope — never serve
            return CacheHit(
                answer=payload.get("answer", ""),
                query_text=payload.get("query_text", ""),
                score=float(p.score),
                collection_ids=list(entry_colls),
                document_ids=list(payload.get("document_ids", [])),
            )
        return None

    # ----------------------------------------------------------------- store
    def store(
        self,
        query: str,
        answer: str,
        source_collection_ids: set[uuid.UUID],
        source_document_ids: set[uuid.UUID],
    ) -> uuid.UUID:
        self.ensure_collection()
        entry_id = uuid.uuid4()
        coll_ids = [str(c) for c in source_collection_ids]
        doc_ids = [str(d) for d in source_document_ids]
        self.client.upsert(self.collection, points=[models.PointStruct(
            id=str(entry_id),
            vector={DENSE: self.embedder.embed_dense(query)},
            payload={
                "answer": answer,
                "query_text": query,
                "collection_ids": coll_ids,
                "document_ids": doc_ids,
                "permission_hash": _permission_hash(coll_ids),
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
