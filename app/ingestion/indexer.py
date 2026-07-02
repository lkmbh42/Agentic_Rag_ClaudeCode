"""Synchronous document indexer (runs in the worker).

Idempotent: re-indexing a document first clears its existing chunks (Postgres)
and points (Qdrant), so re-version/reindex never leaves orphans or duplicates.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

from app.ingestion import storage
from app.ingestion.embedder import Embedder
from app.ingestion.hashing import text_hash
from app.ingestion.pipeline import run_pipeline
from app.ingestion.qdrant_index import QdrantIndex
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.enums import DocumentStatus

logger = logging.getLogger("rag.ingestion.indexer")


def _clear_existing(db: Session, qindex: QdrantIndex, document_id: uuid.UUID) -> None:
    db.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    qindex.delete_by_document(document_id)


def index_document(
    db: Session,
    document_id: uuid.UUID,
    *,
    embedder: Embedder | None = None,
    qindex: QdrantIndex | None = None,
) -> int:
    """Parse, chunk, persist, and index a document. Returns the chunk count.

    Raises on failure (caller handles retry/FAILED status).
    """
    if embedder is None:
        from app.retrieval.factory import get_embedder

        embedder = get_embedder()
    qindex = qindex or QdrantIndex()

    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    doc.status = DocumentStatus.PROCESSING
    doc.error = None
    db.commit()

    try:
        data = storage.read_document(doc.id, doc.filename)
        chunks, page_count = run_pipeline(data, doc.file_type)

        qindex.ensure_collection()
        _clear_existing(db, qindex, doc.id)

        points = []
        for ch in chunks:
            chunk_id = uuid.uuid4()
            db.add(DocumentChunk(
                id=chunk_id,
                document_id=doc.id,
                collection_id=doc.collection_id,
                file_name=doc.filename,
                file_type=doc.file_type,
                page_number=ch.page_number,
                section_title=ch.section_title,
                chunk_type=ch.chunk_type,
                chunk_index=ch.chunk_index,
                raw_content=ch.raw_content,
                normalized_content=ch.normalized_content,
                source_metadata=ch.source_metadata or None,
                content_hash=text_hash(ch.normalized_content),
            ))
            embed_text = ch.normalized_content or ch.raw_content
            payload = {
                "document_id": str(doc.id),
                "collection_id": str(doc.collection_id),
                "chunk_id": str(chunk_id),
                "chunk_type": ch.chunk_type.value,
                "page_number": ch.page_number,
                "section_title": ch.section_title,
                "file_name": doc.filename,
                "file_type": doc.file_type,
                "content": ch.normalized_content,
            }
            points.append(QdrantIndex.make_point(
                chunk_id,
                embedder.embed_dense(embed_text),
                embedder.embed_sparse(embed_text),
                payload,
            ))

        qindex.upsert_points(points)

        doc.status = DocumentStatus.INDEXED
        doc.page_count = page_count
        db.commit()
        logger.info("indexed document %s: %d chunks", doc.id, len(chunks))
        return len(chunks)
    except Exception as exc:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED
            doc.error = str(exc)[:2000]
            db.commit()
        raise
