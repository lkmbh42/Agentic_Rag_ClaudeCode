from __future__ import annotations

import uuid

from sqlalchemy import Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AccessLevel, PrincipalType, ResourceType


class Permission(UUIDMixin, TimestampMixin, Base):
    """A grant: <principal> may access <resource> at <access_level>.

    principal_id references a user or a department (per principal_type);
    resource_id references a collection or a document (per resource_type).
    These are intentionally not DB foreign keys because the target table varies
    by type; referential cleanup is handled in the admin/lifecycle layer.
    """

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint(
            "principal_type",
            "principal_id",
            "resource_type",
            "resource_id",
            name="uq_permission_principal_resource",
        ),
    )

    principal_type: Mapped[PrincipalType] = mapped_column(
        Enum(PrincipalType, name="principal_type"), nullable=False, index=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, name="resource_type"), nullable=False, index=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    access_level: Mapped[AccessLevel] = mapped_column(
        Enum(AccessLevel, name="access_level"),
        default=AccessLevel.READ,
        nullable=False,
    )
