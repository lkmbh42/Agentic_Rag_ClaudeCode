"""ACL payload validation for indexed objects (Phase 2, Rule 5).

Every retrievable object — text/table/figure chunk in `rag_chunks` and page
vector in `docs_pages` — MUST carry the same permission payload schema
(`collection_id` + `document_id`, both non-empty). A single object missing it is
a CRITICAL bug (a retrieval path could return content without an ACL filter).

`audit_collection` scans a Qdrant collection and returns any violations; the
Phase 2 gate test asserts zero, and the Phase 5 red-team reuses it.
"""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient

from app.config import get_settings

_settings = get_settings()

# The ACL keys every retrievable object must carry, non-empty.
REQUIRED_ACL_KEYS = ("collection_id", "document_id")


@dataclass
class AclViolation:
    collection: str
    point_id: str
    missing: list[str]


def audit_collection(client: QdrantClient, collection: str,
                     batch: int = 256) -> list[AclViolation]:
    """Scroll every point and report those missing/empty ACL keys."""
    violations: list[AclViolation] = []
    if not client.collection_exists(collection):
        return violations
    offset = None
    while True:
        points, offset = client.scroll(
            collection, limit=batch, offset=offset,
            with_payload=True, with_vectors=False)
        for p in points:
            payload = p.payload or {}
            missing = [k for k in REQUIRED_ACL_KEYS if not payload.get(k)]
            if missing:
                violations.append(AclViolation(collection, str(p.id), missing))
        if offset is None:
            break
    return violations


def audit_all(client: QdrantClient | None = None) -> list[AclViolation]:
    """Audit both retrievable collections (text chunks + page images)."""
    client = client or QdrantClient(url=_settings.qdrant_url, timeout=30)
    out: list[AclViolation] = []
    for coll in (_settings.qdrant_collection, _settings.docs_pages_collection):
        out.extend(audit_collection(client, coll))
    return out
