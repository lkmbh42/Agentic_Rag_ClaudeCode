"""Visual page retrieval (Phase 3): query → ColQwen2 multivector → `docs_pages`.

The query is embedded per-token by the `colqwen` service; Qdrant scores pages
by MAX_SIM late interaction (the collection's multivector comparator, Phase 2)
and returns the top pages, capped at `visual_top_k_pages` (spec: 4).

Security (Rule 5): the ACL filter (collection_id ∈ allowed) is applied INSIDE
the Qdrant query — non-permitted pages are never candidates, mirroring the text
retriever.

Degradation: dev runs `visual_path=degraded` with no colqwen service and no
`docs_pages` collection. search() returns [] when the visual path is disabled,
the service is unreachable, or the collection is absent — the graph then
answers from the text path alone (never an error to the user).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.ingestion.pages import ColQwenClient, get_colqwen
from app.ingestion.pages_index import PAGES

logger = logging.getLogger("rag.retrieval.visual")
_settings = get_settings()


@dataclass
class RetrievedPage:
    point_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID
    page_number: int
    image_uri: str
    file_name: str | None
    score: float


class VisualRetriever:
    def __init__(
        self,
        colqwen: ColQwenClient | None = None,
        collection: str | None = None,
        url: str | None = None,
    ) -> None:
        self.colqwen = colqwen or get_colqwen()
        self.collection = collection or _settings.docs_pages_collection
        self.client = QdrantClient(url=url or _settings.qdrant_url, timeout=30)

    def search(
        self,
        allowed_collection_ids: set[uuid.UUID],
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedPage]:
        if not allowed_collection_ids or not (query or "").strip():
            return []
        if not self.colqwen.enabled:
            return []  # degraded visual path (dev / CPU host)
        if not self.client.collection_exists(self.collection):
            return []

        try:
            multivector = self.colqwen.embed_query(query)
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the turn
            logger.warning("colqwen query embedding failed: %s", exc)
            return []

        acl = models.Filter(must=[models.FieldCondition(
            key="collection_id",
            match=models.MatchAny(any=[str(c) for c in allowed_collection_ids]),
        )])
        try:
            response = self.client.query_points(
                self.collection,
                query=multivector,
                using=PAGES,
                query_filter=acl,
                limit=top_k or _settings.visual_top_k_pages,
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("docs_pages query failed: %s", exc)
            return []

        results: list[RetrievedPage] = []
        for p in response.points:
            payload = p.payload or {}
            try:
                results.append(RetrievedPage(
                    point_id=uuid.UUID(str(p.id)),
                    document_id=uuid.UUID(payload["document_id"]),
                    collection_id=uuid.UUID(payload["collection_id"]),
                    page_number=int(payload["page_number"]),
                    image_uri=str(payload.get("image_uri", "")),
                    file_name=payload.get("file_name"),
                    score=float(p.score),
                ))
            except (KeyError, ValueError) as exc:
                # A page point without the ACL/provenance payload should not
                # exist (Rule 5 + acl_audit); skip defensively but loudly.
                logger.error("docs_pages point %s has invalid payload: %s", p.id, exc)
        return results
