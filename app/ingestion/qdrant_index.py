"""Qdrant index wrapper (sync).

Collection schema (stable across phases, per ADR 0.2): named vectors
  - "dense"  : size = embedding_dim, cosine
  - "sparse" : learned/lexical sparse
Each point carries ACL + provenance payload so Phase 4 retrieval can filter by
collection_id and cite document_id / page / chunk_type.
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient, models

from app.config import get_settings

_settings = get_settings()

DENSE = "dense"
SPARSE = "sparse"


class QdrantIndex:
    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        self.collection = collection or _settings.qdrant_collection
        self.client = QdrantClient(url=url or _settings.qdrant_url, timeout=30)

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                DENSE: models.VectorParams(
                    size=_settings.embedding_dim, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams()},
        )
        # Payload index on collection_id makes ACL filtering efficient.
        self.client.create_payload_index(
            self.collection, field_name="collection_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            self.collection, field_name="document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    def upsert_points(self, points: list[models.PointStruct]) -> None:
        if points:
            self.client.upsert(self.collection, points=points, wait=True)

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    )
                ])
            ),
            wait=True,
        )

    def count_for_document(self, document_id: uuid.UUID) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(
            self.collection,
            count_filter=models.Filter(must=[
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=str(document_id))
                )
            ]),
            exact=True,
        ).count

    @staticmethod
    def make_point(
        point_id: uuid.UUID,
        dense: list[float],
        sparse: tuple[list[int], list[float]],
        payload: dict,
    ) -> models.PointStruct:
        indices, values = sparse
        return models.PointStruct(
            id=str(point_id),
            vector={
                DENSE: dense,
                SPARSE: models.SparseVector(indices=indices, values=values),
            },
            payload=payload,
        )
