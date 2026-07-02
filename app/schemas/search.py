from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = None
    top_n: int | None = None


class RetrievedChunkOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID
    chunk_type: str
    page_number: int | None
    section_title: str | None
    score: float
    snippet: str


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[RetrievedChunkOut]
