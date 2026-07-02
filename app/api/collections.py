"""Collection listing/detail — ACL-enforced.

Non-admin users only ever see collections they are permitted to read. Fetching a
non-permitted collection by id returns 404 (not 403) so existence isn't leaked.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rbac import accessible_collection_ids, can_access_collection
from app.db.session import get_db
from app.models.collection import Collection
from app.models.user import User
from app.schemas.collection import CollectionOut

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Collection]:
    allowed = await accessible_collection_ids(db, user)
    if not allowed:
        return []
    result = await db.execute(
        select(Collection).where(Collection.id.in_(allowed)).order_by(Collection.name)
    )
    return list(result.scalars().all())


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Collection:
    collection = await db.get(Collection, collection_id)
    if collection is None or not await can_access_collection(db, user, collection_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found"
        )
    return collection
