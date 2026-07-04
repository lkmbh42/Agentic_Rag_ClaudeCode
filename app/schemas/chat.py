from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import MessageRole


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=512)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: uuid.UUID | None = None


class ChatTurnResponse(BaseModel):
    session_id: uuid.UUID
    # Phase 4: id of the persisted assistant message — the feedback anchor.
    message_id: uuid.UUID | None = None
    answer: str
    citations: list[dict] = []
    route: str | None = None
    cache_hit: bool = False
    insufficient: bool = False


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime
    # Phase 4: the requesting user's own rating on this message, if any.
    feedback: str | None = None

    model_config = {"from_attributes": True}


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    reason: str | None = Field(default=None, max_length=2000)


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionDetail(ChatSessionOut):
    messages: list[ChatMessageOut] = []
