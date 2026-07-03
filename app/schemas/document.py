from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DocumentStatus, IngestStatus


class IngestJobOut(BaseModel):
    """Latest ingestion job for a document (Phase 2 admin UI)."""
    status: IngestStatus
    attempt: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    filename: str
    file_type: str
    status: DocumentStatus
    page_count: int | None
    content_hash: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document: DocumentOut
    duplicate: bool
