"""Enumerations shared across models, schemas, and access control.

Stored as native PostgreSQL enum types (created by the initial migration).
"""

from __future__ import annotations

import enum


class Role(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class ChunkType(str, enum.Enum):
    """Content type of a chunk. Populated by the Phase 3 ingestion pipeline;
    defined here so the schema/enum is stable from the start."""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CHART = "chart"
    DIAGRAM = "diagram"
    FORM = "form"
    OCR = "ocr"


class IngestStatus(str, enum.Enum):
    """Lifecycle of one ingestion job (Phase 2). Admin UI displays these;
    CAPTIONING is entered only when the document has figures to caption."""
    QUEUED = "queued"
    PARSING = "parsing"
    CAPTIONING = "captioning"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class PrincipalType(str, enum.Enum):
    USER = "user"
    DEPARTMENT = "department"


class ResourceType(str, enum.Enum):
    COLLECTION = "collection"
    DOCUMENT = "document"


class AccessLevel(str, enum.Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    UPLOAD = "upload"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    ADMIN_ACTION = "admin_action"
    PERMISSION_CHANGE = "permission_change"
    DOCUMENT_DELETE = "document_delete"
    CONVERSATION_DELETE = "conversation_delete"
