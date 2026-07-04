"""ACL-enforced hybrid retrieval endpoint.

The agent graph (Phase 5) calls the same Retriever internally; this authenticated
endpoint exposes it directly for verification and debugging. The accessible
collection set is computed from the DB per request, so results can only ever
include chunks the caller is permitted to read.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rbac import accessible_collection_ids
from app.db.session import get_db
from app.models.user import User
from app.retrieval.retriever import Retriever
from app.retrieval.visual import VisualRetriever
from app.schemas.search import (
    RetrievedChunkOut,
    RetrievedPageOut,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/search", tags=["retrieval"])
_retriever = Retriever()
_visual = VisualRetriever()


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    allowed = await accessible_collection_ids(db, user)
    results = await asyncio.to_thread(
        _retriever.search, allowed, body.query, body.top_k, body.top_n
    )
    pages = []
    if body.include_pages:
        pages = await asyncio.to_thread(_visual.search, allowed, body.query)
    return SearchResponse(
        query=body.query,
        count=len(results),
        pages=[
            RetrievedPageOut(
                document_id=p.document_id, collection_id=p.collection_id,
                page_number=p.page_number, file_name=p.file_name, score=p.score,
            )
            for p in pages
        ],
        results=[
            RetrievedChunkOut(
                chunk_id=r.chunk_id, document_id=r.document_id,
                collection_id=r.collection_id, chunk_type=r.chunk_type,
                page_number=r.page_number, section_title=r.section_title,
                score=r.score, snippet=r.snippet,
            )
            for r in results
        ],
    )
