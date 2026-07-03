from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class EvalResult(UUIDMixin, TimestampMixin, Base):
    """LLM-as-judge scores for one answered request (written by the worker).

    Scores are 0..1. `only_allowed_documents` is a hard security check: did the
    answer draw solely from documents within the user's permitted scope.
    """

    __tablename__ = "eval_results"

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    only_allowed_documents: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
