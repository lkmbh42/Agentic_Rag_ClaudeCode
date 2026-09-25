from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AccessLevel, PrincipalType, ResourceType, Role


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: Role = Role.USER
    department_id: uuid.UUID | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
    department_id: uuid.UUID | None
    is_active: bool

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    is_active: bool | None = None
    role: Role | None = None
    department_id: uuid.UUID | None = None


class ResetCredentialResponse(BaseModel):
    user_id: uuid.UUID
    temporary_password: str


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    department_id: uuid.UUID | None = None


class PermissionUpdate(BaseModel):
    access_level: AccessLevel


class PermissionCreate(BaseModel):
    principal_type: PrincipalType
    principal_id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    access_level: AccessLevel = AccessLevel.READ


class PermissionOut(BaseModel):
    id: uuid.UUID
    principal_type: PrincipalType
    principal_id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    access_level: AccessLevel

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    created_at: datetime  # an audit trail without timestamps can't answer "when?"

    model_config = {"from_attributes": True}


class KnowledgeGapItem(BaseModel):
    question: str            # latest phrasing of the (normalized) question
    count: int               # times asked with a gap answer in the window
    users: int               # distinct askers (count only — never identities)
    last_asked: datetime
    kinds: list[str]         # no_evidence | declined | negative_feedback
    sample_answer: str       # the latest answer, truncated
    feedback_reasons: list[str]


class KnowledgeGapReport(BaseModel):
    window_days: int
    total_questions: int
    gap_questions: int
    gap_rate: float
    negative_feedback: int
    items: list[KnowledgeGapItem]
