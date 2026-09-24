"""Hybrid retriever: dense + sparse search fused with RRF, ACL-filtered, reranked.

Security: the ACL filter (collection_id ∈ allowed) is applied inside *both* Qdrant
prefetches, so non-permitted chunks are never even candidates — the permission
check is enforced at query time in the store, not post-filtered in Python.
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.ingestion.embedder import Embedder
from app.ingestion.qdrant_index import DENSE, SPARSE
from app.retrieval.factory import get_embedder, get_reranker
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk

_settings = get_settings()


class Retriever:
    def __init__(
        self,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        collection: str | None = None,
        url: str | None = None,
    ) -> None:
        self.embedder = embedder or get_embedder()
        self.reranker = reranker or get_reranker()
        self.collection = collection or _settings.qdrant_collection
        self.client = QdrantClient(url=url or _settings.qdrant_url, timeout=30)

    def _acl_filter(self, allowed: list[str]) -> models.Filter:
        return models.Filter(must=[
            models.FieldCondition(key="collection_id", match=models.MatchAny(any=allowed))
        ])

    def search(
        self,
        allowed_collection_ids: set[uuid.UUID],
        query: str,
        top_k: int | None = None,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if not allowed_collection_ids or not query.strip():
            return []
        if not self.client.collection_exists(self.collection):
            return []

        top_k = top_k or _settings.retrieval_top_k
        top_n = top_n or _settings.retrieval_top_n
        allowed = [str(c) for c in allowed_collection_ids]
        acl = self._acl_filter(allowed)

        dense = self.embedder.embed_dense(query)
        s_idx, s_val = self.embedder.embed_sparse(query)

        # Native RRF fusion over a dense prefetch and a sparse prefetch.
        response = self.client.query_points(
            self.collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, filter=acl, limit=top_k),
                models.Prefetch(
                    query=models.SparseVector(indices=s_idx, values=s_val),
                    using=SPARSE, filter=acl, limit=top_k,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        points = response.points
        if not points:
            return []

        # Cross-encoder / lexical rerank, then keep top-n.
        docs = [(p.payload or {}).get("content", "") for p in points]
        rerank_scores = self.reranker.rerank(query, docs)
        order = sorted(range(len(points)), key=lambda i: rerank_scores[i], reverse=True)

        # Relevance gate: drop chunks scoring far below the best match so obvious
        # off-topic noise never reaches the generator (matters most with the weak
        # dev embedder; harmless with the prod cross-encoder). Falls back to the
        # full ordering if every score is zero.
        #
        # The factor is deliberately low (0.05, not 0.15): the cross-encoder scores
        # table/figure chunks well below a matching *heading* (bare numbers share
        # no words with the question), yet those chunks carry the actual answer in
        # a table-heavy corpus. 0.15×a strong heading was clipping the very table
        # the user asked for while true noise still sits an order of magnitude
        # lower — so 0.05 keeps the table and still rejects the junk. top_n caps
        # the final count regardless.
        if rerank_scores:
            best = max(rerank_scores)
            if best > 0:
                gated = [i for i in order if rerank_scores[i] >= best * 0.05]
                order = gated or order

        results: list[RetrievedChunk] = []
        for rank, i in enumerate(order[:top_n]):
            p = points[i]
            payload = p.payload or {}
            content = payload.get("content", "")
            results.append(RetrievedChunk(
                chunk_id=uuid.UUID(str(p.id)),
                document_id=uuid.UUID(payload["document_id"]),
                collection_id=uuid.UUID(payload["collection_id"]),
                chunk_type=payload.get("chunk_type", "text"),
                page_number=payload.get("page_number"),
                section_title=payload.get("section_title"),
                score=float(rerank_scores[i]),
                snippet=content[:300],
                content=content,
                file_name=payload.get("file_name"),
                image_uri=payload.get("image_uri"),
            ))
        return results
