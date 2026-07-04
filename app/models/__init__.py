"""Importing this package registers every model on Base.metadata.

Alembic autogenerate and create_all both rely on these imports, so keep them
exhaustive.
"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.chat import ChatMessage, ChatSession, MessageFeedback
from app.models.chunk import DocumentChunk
from app.models.collection import Collection
from app.models.department import Department
from app.models.document import Document
from app.models.eval import EvalResult
from app.models.ingest import IngestJob
from app.models.permission import Permission
from app.models.user import User

__all__ = [
    "Base",
    "AuditLog",
    "ChatMessage",
    "ChatSession",
    "MessageFeedback",
    "DocumentChunk",
    "Collection",
    "Department",
    "Document",
    "EvalResult",
    "IngestJob",
    "Permission",
    "User",
]
