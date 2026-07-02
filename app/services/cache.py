"""Async wrappers over the (sync) SemanticCache invalidation, called from the
document lifecycle (delete / re-version) and permission changes.

These run the sync Qdrant/Redis work off the event loop. They evict exactly the
cache entries whose source scope included the affected document/collection — a
security requirement (no stale answer may reference removed or newly-forbidden
content).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger("rag.cache")


async def invalidate_document(document_id: uuid.UUID) -> int:
    from app.retrieval.semantic_cache import SemanticCache

    n = await asyncio.to_thread(SemanticCache().invalidate_document, document_id)
    if n:
        logger.info("invalidated %d cache entries for document %s", n, document_id)
    return n


async def invalidate_collection(collection_id: uuid.UUID) -> int:
    from app.retrieval.semantic_cache import SemanticCache

    n = await asyncio.to_thread(SemanticCache().invalidate_collection, collection_id)
    if n:
        logger.info("invalidated %d cache entries for collection %s", n, collection_id)
    return n
