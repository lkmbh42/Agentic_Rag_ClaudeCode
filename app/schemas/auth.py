from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access-token lifetime in seconds


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
    department_id: uuid.UUID | None
    is_active: bool

    model_config = {"from_attributes": True}
