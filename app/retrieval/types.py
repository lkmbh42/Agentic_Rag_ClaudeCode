from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID
    chunk_type: str
    page_number: int | None
    section_title: str | None
    score: float
    snippet: str
    content: str
    file_name: str | None = None
