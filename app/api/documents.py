"""Document API: upload (dedup), list, detail, reindex, delete (cascade).

All routes are ACL-scoped to collections the user may access.
"""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rbac import accessible_collection_ids, can_access_collection
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentOut, DocumentUploadResponse
from app.services import documents as docsvc

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    collection_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    doc, duplicate = await docsvc.create_document(
        db, user, collection_id, file.filename or "upload.bin", data
    )
    return DocumentUploadResponse(document=DocumentOut.model_validate(doc), duplicate=duplicate)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    collection_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    allowed = await accessible_collection_ids(db, user)
    if not allowed:
        return []
    if collection_id is not None:
        if collection_id not in allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
        allowed = {collection_id}
    result = await db.execute(
        select(Document)
        .where(Document.collection_id.in_(allowed))
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    doc = await db.get(Document, document_id)
    if doc is None or not await can_access_collection(db, user, doc.collection_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.post("/{document_id}/reindex", response_model=DocumentOut)
async def reindex_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    return await docsvc.reindex_document(db, user, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import Response

    await docsvc.delete_document(db, user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
