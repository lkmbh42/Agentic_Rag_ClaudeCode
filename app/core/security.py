"""Password hashing and JWT creation/validation.

JWT model (ADR 0.5): short-lived access tokens + refresh-token rotation, with a
Redis jti denylist (see app/core/redis.py) for immediate revocation. Every token
carries a unique `jti` so it can be individually revoked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

_settings = get_settings()

ACCESS = "access"
REFRESH = "refresh"

# bcrypt operates on at most 72 bytes; longer inputs must be truncated by the
# caller (bcrypt 5.x raises rather than silently truncating). We use the
# `bcrypt` library directly — passlib is unmaintained and breaks on bcrypt 5.x.
_BCRYPT_MAX_BYTES = 72


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def _to_bcrypt_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IssuedToken:
    token: str
    jti: str
    expires_at: datetime


def _create_token(
    *, subject: uuid.UUID, role: str, department_id: uuid.UUID | None,
    token_type: str, ttl: timedelta,
) -> IssuedToken:
    now = datetime.now(timezone.utc)
    expires_at = now + ttl
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "dept": str(department_id) if department_id else None,
        "type": token_type,
        "jti": jti,
        # Sub-second iat so session-epoch revocation is precise (a token issued
        # just after a bump in the same second is still strictly newer).
        "iat": now.timestamp(),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)
    return IssuedToken(token=token, jti=jti, expires_at=expires_at)


def create_access_token(
    subject: uuid.UUID, role: str, department_id: uuid.UUID | None
) -> IssuedToken:
    return _create_token(
        subject=subject, role=role, department_id=department_id,
        token_type=ACCESS, ttl=timedelta(minutes=_settings.access_token_ttl_min),
    )


def create_refresh_token(
    subject: uuid.UUID, role: str, department_id: uuid.UUID | None
) -> IssuedToken:
    return _create_token(
        subject=subject, role=role, department_id=department_id,
        token_type=REFRESH, ttl=timedelta(days=_settings.refresh_token_ttl_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify signature + expiry. Raises jose.JWTError on failure."""
    return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])


__all__ = [
    "ACCESS",
    "REFRESH",
    "IssuedToken",
    "JWTError",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
]
