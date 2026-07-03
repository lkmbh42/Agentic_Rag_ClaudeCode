"""Qdrant `docs_pages` multivector index for ColQwen2 page embeddings (Phase 2).

ColQwen2 encodes a page image into MANY per-patch vectors; retrieval scores by
MAX_SIM (late interaction). Qdrant models this as a multivector collection with
`MultiVectorComparator.MAX_SIM`. Binary quantization is enabled (spec) to cut
the multivector storage ~32×.

ACL invariant (Rule 5): every page point carries the SAME permission payload
schema as text chunks — `collection_id` + `document_id` — so the visual path
filters identically. `page_payload()` is the single source of that schema.
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient, models

from app.config import get_settings

_settings = get_settings()

PAGES = "pages"  # named multivector


def page_payload(*, document_id: uuid.UUID | str, collection_id: uuid.UUID | str,
                 page_number: int, image_uri: str, file_name: str,
                 file_type: str) -> dict:
    """The ACL + provenance payload for a page point. Identical ACL keys
    (`collection_id`, `document_id`) to the text schema — see qdrant_index."""
    return {
        "document_id": str(document_id),
        "collection_id": str(collection_id),
        "page_number": page_number,
        "image_uri": image_uri,
        "file_name": file_name,
        "file_type": file_type,
        "modality": "page_image",
    }


class PagesIndex:
    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        self.collection = collection or _settings.docs_pages_collection
        self.client = QdrantClient(url=url or _settings.qdrant_url, timeout=60)

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        quant = None
        if _settings.docs_pages_binary_quantization:
            quant = models.BinaryQuantization(
                binary=models.BinaryQuantizationConfig(always_ram=True))
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                PAGES: models.VectorParams(
                    size=_settings.colqwen_dim,
                    distance=models.Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM),
                    quantization_config=quant,
                )
            },
        )
        for field in ("collection_id", "document_id"):
            self.client.create_payload_index(
                self.collection, field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD)

    def upsert_pages(self, points: list[models.PointStruct]) -> None:
        if points:
            self.client.upsert(self.collection, points=points, wait=True)

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        if not self.client.collection_exists(self.collection):
            return
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="document_id",
                                      match=models.MatchValue(value=str(document_id)))])),
            wait=True,
        )

    def count_for_document(self, document_id: uuid.UUID) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(
            self.collection,
            count_filter=models.Filter(must=[
                models.FieldCondition(key="document_id",
                                      match=models.MatchValue(value=str(document_id)))]),
            exact=True,
        ).count

    @staticmethod
    def make_point(point_id: uuid.UUID, multivector: list[list[float]],
                   payload: dict) -> models.PointStruct:
        return models.PointStruct(
            id=str(point_id), vector={PAGES: multivector}, payload=payload)
