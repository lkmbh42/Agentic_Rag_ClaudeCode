"""Document lifecycle: upload (with dedup), reindex/re-version, delete (cascade).

Delete cascade (lifecycle/security requirement):
  Postgres document row  -> chunks via ON DELETE CASCADE
  Qdrant points          -> delete_by_document
  Semantic cache         -> invalidate_document
No orphaned vectors; no cached answer can reference a deleted document.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import can_access_collection
from app.ingestion import filetype, storage
from app.ingestion.hashing import content_hash
from app.ingestion.qdrant_index import QdrantIndex
from app.models.document import Document
from app.models.enums import AuditAction, DocumentStatus
from app.models.user import User
from app.queue import enqueue_index
from app.services.audit import record_audit
from app.services.cache import invalidate_document


async def create_document(
    db: AsyncSession, user: User, collection_id: uuid.UUID, filename: str, data: bytes
) -> tuple[Document, bool]:
    if not await can_access_collection(db, user, collection_id):
        # 404, not 403 — don't reveal collections the user can't see.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")

    try:
        file_type = filetype.detect(filename, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    digest = content_hash(data)

    existing = (
        await db.execute(
            select(Document).where(
                Document.collection_id == collection_id,
                Document.content_hash == digest,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Idempotent: identical content is a duplicate, not a re-index.
        return existing, True

    doc = Document(
        collection_id=collection_id,
        filename=filename,
        file_type=file_type,
        content_hash=digest,
        status=DocumentStatus.PENDING,
    )
    db.add(doc)
    await db.flush()
    storage.save_document(doc.id, doc.filename, data)
    await record_audit(
        db, action=AuditAction.UPLOAD, user_id=user.id,
        resource_type="document", resource_id=str(doc.id),
        detail={"filename": filename, "file_type": file_type},
    )
    await db.commit()
    await db.refresh(doc)

    await enqueue_index(doc.id)
    return doc, False


async def reindex_document(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    doc = await _get_accessible(db, user, document_id)
    doc.status = DocumentStatus.PENDING
    doc.error = None
    await db.commit()
    await db.refresh(doc)
    await enqueue_index(doc.id)
    return doc


async def delete_document(db: AsyncSession, user: User, document_id: uuid.UUID) -> None:
    doc = await _get_accessible(db, user, document_id)
    doc_id = doc.id
    collection_id = doc.collection_id

    # Qdrant first (sync client off the event loop), then cache, then Postgres.
    qindex = QdrantIndex()
    await asyncio.to_thread(qindex.delete_by_document, doc_id)
    await invalidate_document(doc_id)
    storage.delete_document_files(doc_id)

    await record_audit(
        db, action=AuditAction.DOCUMENT_DELETE, user_id=user.id,
        resource_type="document", resource_id=str(doc_id),
        detail={"collection_id": str(collection_id)},
    )
    await db.delete(doc)  # chunks cascade in Postgres
    await db.commit()


async def _get_accessible(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    doc = await db.get(Document, document_id)
    if doc is None or not await can_access_collection(db, user, doc.collection_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc
