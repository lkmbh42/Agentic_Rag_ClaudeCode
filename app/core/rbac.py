"""Document/collection access control — the security core of retrieval.

Effective READ access to a collection for user U:
  - U is an admin                                  -> allowed (all collections)
  - the collection is owned by U's department      -> allowed
  - a permission grants U (as user) the collection -> allowed
  - a permission grants U's department the collection -> allowed
  - otherwise                                      -> denied

`accessible_collection_ids` returns the full allowed set and is what the Phase 4
retriever will turn into a Qdrant filter so non-permitted chunks are never even
candidates. All checks are enforced server-side from the DB; nothing trusts the
client.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.document import Document
from app.models.enums import PrincipalType, ResourceType, Role
from app.models.permission import Permission
from app.models.user import User


async def accessible_collection_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    """All collection ids the user may read. Admins get every collection."""
    if user.role == Role.ADMIN:
        rows = await db.execute(select(Collection.id))
        return set(rows.scalars().all())

    allowed: set[uuid.UUID] = set()

    # Own-department collections.
    if user.department_id is not None:
        rows = await db.execute(
            select(Collection.id).where(
                Collection.department_id == user.department_id
            )
        )
        allowed.update(rows.scalars().all())

    # Explicit grants to the user or to the user's department.
    principals: list[tuple[PrincipalType, uuid.UUID]] = [
        (PrincipalType.USER, user.id)
    ]
    if user.department_id is not None:
        principals.append((PrincipalType.DEPARTMENT, user.department_id))

    for principal_type, principal_id in principals:
        rows = await db.execute(
            select(Permission.resource_id).where(
                Permission.resource_type == ResourceType.COLLECTION,
                Permission.principal_type == principal_type,
                Permission.principal_id == principal_id,
            )
        )
        allowed.update(rows.scalars().all())

    return allowed


async def can_access_collection(
    db: AsyncSession, user: User, collection_id: uuid.UUID
) -> bool:
    if user.role == Role.ADMIN:
        return True
    return collection_id in await accessible_collection_ids(db, user)


async def can_access_document(
    db: AsyncSession, user: User, document: Document
) -> bool:
    """A document is readable if its collection is readable, or an explicit
    document-level permission grants the user/department access."""
    if user.role == Role.ADMIN:
        return True
    if await can_access_collection(db, user, document.collection_id):
        return True

    principals: list[tuple[PrincipalType, uuid.UUID]] = [
        (PrincipalType.USER, user.id)
    ]
    if user.department_id is not None:
        principals.append((PrincipalType.DEPARTMENT, user.department_id))

    for principal_type, principal_id in principals:
        row = await db.execute(
            select(Permission.id).where(
                Permission.resource_type == ResourceType.DOCUMENT,
                Permission.resource_id == document.id,
                Permission.principal_type == principal_type,
                Permission.principal_id == principal_id,
            )
        )
        if row.first() is not None:
            return True
    return False
