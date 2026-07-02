"""Admin endpoints (role=admin) — org/user/collection/permission management.

These are ordinary RBAC-gated API calls; the Phase 9 admin SPA consumes them.
Every route depends on require_admin, so a non-admin JWT is rejected with 403.
This phase ships the management primitives needed to set up and test ACLs; the
full admin surface (suspend/revoke-sessions, reindex, metrics) lands in later
phases.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.redis import bump_session_epoch
from app.core.security import hash_password
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.collection import Collection
from app.models.department import Department
from app.models.document import Document
from app.models.enums import AuditAction, ResourceType
from app.models.eval import EvalResult
from app.models.permission import Permission
from app.models.user import User
from app.observability import metrics
from app.schemas.admin import (
    AuditLogOut,
    CollectionCreate,
    DepartmentCreate,
    DepartmentOut,
    PermissionCreate,
    PermissionOut,
    PermissionUpdate,
    ResetCredentialResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.collection import CollectionOut
from app.services.audit import record_audit
from app.services.cache import invalidate_collection, invalidate_document

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    body: DepartmentCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Department:
    dept = Department(name=body.name)
    db.add(dept)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Department already exists") from exc
    await record_audit(
        db, action=AuditAction.ADMIN_ACTION, user_id=admin.id,
        resource_type="department", resource_id=str(dept.id),
        detail={"op": "create_department", "name": body.name},
    )
    await db.commit()
    await db.refresh(dept)
    return dept


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    if body.department_id is not None and await db.get(Department, body.department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown department_id")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
        department_id=body.department_id,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc
    await record_audit(
        db, action=AuditAction.ADMIN_ACTION, user_id=admin.id,
        resource_type="user", resource_id=str(user.id),
        detail={"op": "create_user", "email": body.email, "role": body.role.value},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/collections", response_model=CollectionOut, status_code=201)
async def create_collection(
    body: CollectionCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Collection:
    if body.department_id is not None and await db.get(Department, body.department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown department_id")
    collection = Collection(
        name=body.name, description=body.description, department_id=body.department_id
    )
    db.add(collection)
    await db.flush()
    await record_audit(
        db, action=AuditAction.ADMIN_ACTION, user_id=admin.id,
        resource_type="collection", resource_id=str(collection.id),
        detail={"op": "create_collection", "name": body.name},
    )
    await db.commit()
    await db.refresh(collection)
    return collection


@router.post("/permissions", response_model=PermissionOut, status_code=201)
async def grant_permission(
    body: PermissionCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Permission:
    perm = Permission(
        principal_type=body.principal_type,
        principal_id=body.principal_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        access_level=body.access_level,
    )
    db.add(perm)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Permission already exists") from exc
    await record_audit(
        db, action=AuditAction.PERMISSION_CHANGE, user_id=admin.id,
        resource_type=body.resource_type.value, resource_id=str(body.resource_id),
        detail={"op": "grant", "principal_type": body.principal_type.value,
                "principal_id": str(body.principal_id)},
    )
    await db.commit()
    await db.refresh(perm)
    return perm


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------- listings
@router.get("/users", response_model=list[UserOut])
async def list_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(User).order_by(User.email))).scalars().all())


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Department).order_by(Department.name))).scalars().all())


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Collection).order_by(Collection.name))).scalars().all())


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return list((await db.execute(select(Permission))).scalars().all())


# ----------------------------------------------------------- user lifecycle ops
@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    suspended = False
    if body.role is not None:
        user.role = body.role
    if body.department_id is not None:
        user.department_id = body.department_id
    if body.is_active is not None:
        if user.is_active and body.is_active is False:
            suspended = True
        user.is_active = body.is_active
    # Suspending terminates active sessions immediately (epoch bump + is_active).
    if suspended:
        await bump_session_epoch(user_id)
    await record_audit(
        db, action=AuditAction.ADMIN_ACTION, user_id=admin.id,
        resource_type="user", resource_id=str(user_id),
        detail={"op": "update_user", "suspended": suspended},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
async def revoke_sessions(
    user_id: uuid.UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    from fastapi import Response

    if await db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    await bump_session_epoch(user_id)
    await record_audit(db, action=AuditAction.ADMIN_ACTION, user_id=admin.id,
                       resource_type="user", resource_id=str(user_id),
                       detail={"op": "revoke_sessions"})
    await db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/reset-credential", response_model=ResetCredentialResponse)
async def reset_credential(
    user_id: uuid.UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> ResetCredentialResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    temp = secrets.token_urlsafe(12)
    user.hashed_password = hash_password(temp)
    await bump_session_epoch(user_id)  # old sessions die with the old credential
    await record_audit(db, action=AuditAction.ADMIN_ACTION, user_id=admin.id,
                       resource_type="user", resource_id=str(user_id),
                       detail={"op": "reset_credential"})
    await db.commit()
    return ResetCredentialResponse(user_id=user_id, temporary_password=temp)


# ------------------------------------------------------- permission edit/revoke
async def _invalidate_for_permission(perm: Permission) -> None:
    """Evict cache entries whose scope included the affected resource (security)."""
    if perm.resource_type == ResourceType.COLLECTION:
        await invalidate_collection(perm.resource_id)
    else:
        await invalidate_document(perm.resource_id)


@router.patch("/permissions/{permission_id}", response_model=PermissionOut)
async def edit_permission(
    permission_id: uuid.UUID, body: PermissionUpdate,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
) -> Permission:
    perm = await db.get(Permission, permission_id)
    if perm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission not found")
    perm.access_level = body.access_level
    await _invalidate_for_permission(perm)
    await record_audit(db, action=AuditAction.PERMISSION_CHANGE, user_id=admin.id,
                       resource_type=perm.resource_type.value, resource_id=str(perm.resource_id),
                       detail={"op": "edit", "access_level": body.access_level.value})
    await db.commit()
    await db.refresh(perm)
    return perm


@router.delete("/permissions/{permission_id}", status_code=204)
async def revoke_permission(
    permission_id: uuid.UUID, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    from fastapi import Response

    perm = await db.get(Permission, permission_id)
    if perm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission not found")
    # Revoking access MUST invalidate any cached answer that used the resource.
    await _invalidate_for_permission(perm)
    await record_audit(db, action=AuditAction.PERMISSION_CHANGE, user_id=admin.id,
                       resource_type=perm.resource_type.value, resource_id=str(perm.resource_id),
                       detail={"op": "revoke"})
    await db.delete(perm)
    await db.commit()
    return Response(status_code=204)


# ----------------------------------------------------------------- live ops
@router.get("/metrics")
async def admin_metrics(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict:
    summary = await metrics.summary(db)
    users = (await db.execute(select(func.count(User.id)))).scalar_one()
    docs = (await db.execute(select(func.count(Document.id)))).scalar_one()
    colls = (await db.execute(select(func.count(Collection.id)))).scalar_one()
    eval_avgs = (await db.execute(select(
        func.count(EvalResult.id),
        func.avg(EvalResult.faithfulness),
        func.avg(EvalResult.answer_relevancy),
        func.avg(EvalResult.citation_accuracy),
    ))).one()
    return {
        **summary,
        "counts": {"users": users, "documents": docs, "collections": colls},
        "eval": {
            "scored": eval_avgs[0],
            "avg_faithfulness": round(float(eval_avgs[1]), 3) if eval_avgs[1] is not None else None,
            "avg_answer_relevancy": round(float(eval_avgs[2]), 3) if eval_avgs[2] is not None else None,
            "avg_citation_accuracy": round(float(eval_avgs[3]), 3) if eval_avgs[3] is not None else None,
        },
    }
