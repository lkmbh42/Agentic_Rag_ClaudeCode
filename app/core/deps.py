"""Authentication dependencies: resolve and authorize the current user.

A valid request must present a Bearer access token that:
  - has a valid signature and is unexpired,
  - is of type "access" (refresh tokens cannot authenticate requests),
  - has a jti that is not on the revocation denylist,
  - maps to an existing, active user.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.redis import is_revoked, session_epoch
from app.db.session import get_db
from app.models.enums import Role
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_EXC
    try:
        payload = security.decode_token(creds.credentials)
    except security.JWTError as exc:
        raise _CREDENTIALS_EXC from exc

    if payload.get("type") != security.ACCESS:
        raise _CREDENTIALS_EXC

    jti = payload.get("jti")
    if not jti or await is_revoked(jti):
        raise _CREDENTIALS_EXC

    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(sub)
    except (TypeError, ValueError) as exc:
        raise _CREDENTIALS_EXC from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC

    # Bulk revocation: tokens issued before the user's session epoch are invalid
    # (admin revoke-sessions / suspend / credential reset bump the epoch).
    if float(payload.get("iat", 0)) < await session_epoch(user.id):
        raise _CREDENTIALS_EXC
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return user
