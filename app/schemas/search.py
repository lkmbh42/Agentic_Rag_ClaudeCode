from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = None
    top_n: int | None = None
    # Phase 3: also run ColQwen2 page retrieval (empty when the visual path is
    # degraded). Used by the retrieval eval to score visual hit@5.
    include_pages: bool = False


class RetrievedChunkOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID
    chunk_type: str
    page_number: int | None
    section_title: str | None
    score: float
    snippet: str


class RetrievedPageOut(BaseModel):
    document_id: uuid.UUID
    collection_id: uuid.UUID
    page_number: int
    file_name: str | None
    score: float


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[RetrievedChunkOut]
    pages: list[RetrievedPageOut] = []
