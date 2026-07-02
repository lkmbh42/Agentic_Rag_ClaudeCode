"""Authentication: login, refresh rotation, logout, current-user."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import security
from app.core.deps import get_current_user
from app.core.redis import is_revoked, revoke_jti, session_epoch
from app.db.session import get_db
from app.models.enums import AuditAction
from app.models.user import User
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()
_bearer = HTTPBearer(auto_error=True)


def _client_ip(request: Request) -> str | None:
    # Behind the prod nginx proxy the socket peer is the proxy; prefer the
    # forwarded client (first hop) when present.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _ttl_seconds(exp: int) -> int:
    return max(0, exp - int(datetime.now(timezone.utc).timestamp()))


def _issue_pair(user: User) -> TokenResponse:
    access = security.create_access_token(user.id, user.role.value, user.department_id)
    refresh = security.create_refresh_token(user.id, user.role.value, user.department_id)
    return TokenResponse(
        access_token=access.token,
        refresh_token=refresh.token,
        expires_in=_settings.access_token_ttl_min * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not security.verify_password(body.password, user.hashed_password):
        await record_audit(
            db,
            action=AuditAction.LOGIN_FAILED,
            user_id=user.id if user else None,
            detail={"email": body.email},
            ip_address=_client_ip(request),
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if not user.is_active:
        await record_audit(
            db,
            action=AuditAction.LOGIN_FAILED,
            user_id=user.id,
            detail={"email": body.email, "reason": "account_disabled"},
            ip_address=_client_ip(request),
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )

    tokens = _issue_pair(user)
    await record_audit(
        db, action=AuditAction.LOGIN, user_id=user.id, ip_address=_client_ip(request)
    )
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        payload = security.decode_token(body.refresh_token)
    except security.JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    if payload.get("type") != security.REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token"
        )

    jti = payload.get("jti")
    if not jti or await is_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked"
        )

    try:
        user_id = uuid.UUID(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    # Bulk revocation applies to refresh tokens too: a token issued before the
    # user's session epoch (admin revoke-sessions / credential reset) must not
    # be able to mint a fresh pair.
    if float(payload.get("iat", 0)) < await session_epoch(user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked"
        )

    # Rotation: invalidate the presented refresh token so it cannot be reused.
    await revoke_jti(jti, _ttl_seconds(payload["exp"]))

    tokens = _issue_pair(user)
    await record_audit(
        db, action=AuditAction.TOKEN_REFRESH, user_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke the presented access token immediately (denylist its jti)."""
    payload = security.decode_token(creds.credentials)
    await revoke_jti(payload["jti"], _ttl_seconds(payload["exp"]))
    await record_audit(db, action=AuditAction.LOGOUT, user_id=user.id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=CurrentUser)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
