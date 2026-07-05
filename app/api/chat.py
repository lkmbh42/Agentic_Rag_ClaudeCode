"""Chat sessions — ownership-enforced (authorization, not just authentication).

A non-admin must never read another user's session by guessing an id. Any
session-scoped endpoint verifies ownership; a non-owned id returns 404 so
existence isn't leaked. (The full streaming /chat generation endpoint arrives in
Phases 5–6; this phase establishes session ownership and the schema.)
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.core.deps import get_current_user
from app.core.ratelimit import rate_limit
from app.core.rbac import accessible_collection_ids
from app.db.session import get_db
from app.llm.client import llm_available
from app.models.chat import ChatMessage, ChatSession, MessageFeedback
from app.models.enums import AuditAction, MessageRole
from app.models.user import User
from app.observability import metrics, tracing
from app.services.audit import record_audit
from app.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    ChatTurnResponse,
    FeedbackRequest,
)

router = APIRouter(prefix="/chat", tags=["chat"])
_settings = get_settings()


def _require_llm_backend() -> None:
    """Fail fast with an explicit 503 when the LLM backend is down (Phase 1
    graceful degradation) instead of running the graph into empty answers."""
    if not llm_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM backend ({_settings.llm_backend}) is unavailable — "
                   "please try again shortly",
        )


def _generation_audit_detail(result: dict, request_id: str, *, streamed: bool = False) -> dict:
    """Audit detail for a GENERATION event (Phase 5 §3: the audit log must cover
    the query, the retrieved document ids, and an answer hash). The answer is
    hashed, not stored, so the tamper-evident trail never duplicates message
    content (which lives in chat_messages) or bloats the audit table."""
    import hashlib

    chunks = result.get("chunks", [])
    retrieved = sorted({c.get("document_id") for c in chunks if c.get("document_id")})
    answer = result.get("answer", "") or ""
    return {
        "request_id": request_id,
        "route": result.get("route"),
        "cache_hit": result.get("cache_hit", False),
        "insufficient": result.get("insufficient", False),
        "streamed": streamed,
        "query": result.get("query", ""),
        "retrieved_document_ids": retrieved,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
    }


async def _owned_session(
    session_id: uuid.UUID, user: User, db: AsyncSession
) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return session


@router.post("", response_model=ChatTurnResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(rate_limit),
    db: AsyncSession = Depends(get_db),
) -> ChatTurnResponse:
    """Run one agent-graph turn. The chat session id is the graph thread_id, so
    multi-turn context persists (Postgres checkpointer) across requests/restarts."""
    _require_llm_backend()
    if body.session_id is not None:
        session = await _owned_session(body.session_id, user, db)
    else:
        session = ChatSession(user_id=user.id, title=body.message[:80])
        db.add(session)
        await db.flush()

    allowed = await accessible_collection_ids(db, user)
    db.add(ChatMessage(session_id=session.id, role=MessageRole.USER, content=body.message))
    await db.commit()

    # The graph is sync (CPU + sync clients); run it off the event loop with a
    # hard request-duration circuit breaker.
    from app.graph.runtime import get_graph

    graph = get_graph()
    request_id = str(uuid.uuid4())
    initial = {
        "messages": [{"role": "user", "content": body.message}],
        "query": body.message,
        "allowed_collection_ids": [str(c) for c in allowed],
        "request_id": request_id,
        "iterations": 0, "retrieval_retries": 0, "generation_retries": 0,
    }
    config = {"configurable": {"thread_id": str(session.id)},
              "recursion_limit": _settings.max_graph_iterations * 3 + 10}
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(graph.invoke, initial, config),
            timeout=_settings.max_request_duration_s,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Request timed out") from exc
    total_ms = (time.perf_counter() - t0) * 1000

    answer = result.get("answer", "")
    assistant_msg = ChatMessage(session_id=session.id, role=MessageRole.ASSISTANT,
                                content=answer)
    db.add(assistant_msg)
    await db.flush()  # id needed in the response (feedback anchor, Phase 4)
    await record_audit(
        db, action=AuditAction.GENERATION, user_id=user.id,
        resource_type="chat_session", resource_id=str(session.id),
        detail=_generation_audit_detail(result, request_id),
    )
    await db.commit()

    # Observability (best-effort; never blocks the response).
    metrics.record_latency(total_ms)
    metrics.record_cache(bool(result.get("cache_hit", False)))
    tracing.record_request(result, total_ms, request_id, user.id)

    return ChatTurnResponse(
        session_id=session.id, message_id=assistant_msg.id, answer=answer,
        citations=result.get("citations", []), route=result.get("route"),
        cache_hit=result.get("cache_hit", False),
        insufficient=result.get("insufficient", False),
    )


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: User = Depends(rate_limit),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """SSE streaming variant of /chat (ADR: SSE token streaming).

    Emits `token` events as the generator produces text, then a `done` event with
    the final answer + citations. Cache-hit / insufficient paths emit no tokens
    and a single terminal `done` event.
    """
    _require_llm_backend()
    if body.session_id is not None:
        session = await _owned_session(body.session_id, user, db)
    else:
        session = ChatSession(user_id=user.id, title=body.message[:80])
        db.add(session)
        await db.flush()

    allowed = await accessible_collection_ids(db, user)
    db.add(ChatMessage(session_id=session.id, role=MessageRole.USER, content=body.message))
    await db.commit()
    session_id = session.id

    from app.graph.runtime import get_graph

    graph = get_graph()
    request_id = str(uuid.uuid4())
    initial = {
        "messages": [{"role": "user", "content": body.message}],
        "query": body.message,
        "allowed_collection_ids": [str(c) for c in allowed],
        "request_id": request_id,
        "iterations": 0, "retrieval_retries": 0, "generation_retries": 0,
    }
    config = {"configurable": {"thread_id": str(session_id)},
              "recursion_limit": _settings.max_graph_iterations * 3 + 10}
    t0 = time.perf_counter()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    def _producer() -> None:
        try:
            for mode, data in graph.stream(initial, config, stream_mode=["custom", "values"]):
                loop.call_soon_threadsafe(queue.put_nowait, (mode, data))
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, ("__error__", str(exc)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, (_SENTINEL, None))

    async def event_gen():
        threading.Thread(target=_producer, daemon=True).start()
        final_state: dict = {}
        while True:
            mode, data = await queue.get()
            if mode is _SENTINEL:
                break
            if mode == "custom":
                yield {"event": "token", "data": json.dumps({"token": data})}
            elif mode == "values":
                final_state = data
            elif mode == "__error__":
                yield {"event": "error", "data": json.dumps({"error": data})}

        total_ms = (time.perf_counter() - t0) * 1000
        answer = final_state.get("answer", "")
        assistant_msg = ChatMessage(session_id=session_id, role=MessageRole.ASSISTANT,
                                    content=answer)
        db.add(assistant_msg)
        await db.flush()
        await record_audit(
            db, action=AuditAction.GENERATION, user_id=user.id,
            resource_type="chat_session", resource_id=str(session_id),
            detail=_generation_audit_detail(final_state, request_id, streamed=True),
        )
        await db.commit()
        metrics.record_latency(total_ms)
        metrics.record_cache(bool(final_state.get("cache_hit", False)))
        tracing.record_request(final_state, total_ms, request_id, user.id)
        yield {"event": "done", "data": json.dumps({
            "session_id": str(session_id), "message_id": str(assistant_msg.id),
            "answer": answer,
            "citations": final_state.get("citations", []),
            "route": final_state.get("route"),
            "cache_hit": final_state.get("cache_hit", False),
            "insufficient": final_state.get("insufficient", False),
        })}

    return EventSourceResponse(event_gen())


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    session = ChatSession(user_id=user.id, title=body.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionDetail:
    session = await _owned_session(session_id, user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = list(result.scalars().all())
    # The requesting user's own ratings (Phase 4 feedback UI state).
    fb: dict[uuid.UUID, str] = {}
    if messages:
        fb_rows = await db.execute(
            select(MessageFeedback).where(
                MessageFeedback.user_id == user.id,
                MessageFeedback.message_id.in_([m.id for m in messages]),
            )
        )
        fb = {f.message_id: f.rating for f in fb_rows.scalars()}
    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        messages=[
            ChatMessageOut(id=m.id, role=m.role, content=m.content,
                           created_at=m.created_at, feedback=fb.get(m.id))
            for m in messages
        ],
    )


@router.post("/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def message_feedback(
    message_id: uuid.UUID,
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """👍/👎 (+ optional reason) on an assistant message the caller owns.
    Upsert per (message, user); persisted to Postgres for eval mining."""
    msg = await db.get(ChatMessage, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    session = await db.get(ChatSession, msg.session_id)
    if session is None or session.user_id != user.id:
        # 404, not 403 — never confirm another user's message ids.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if msg.role != MessageRole.ASSISTANT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Feedback applies to assistant messages")

    existing = (
        await db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.rating, existing.reason = body.rating, body.reason
    else:
        db.add(MessageFeedback(message_id=message_id, user_id=user.id,
                               rating=body.rating, reason=body.reason))
    await db.commit()
    from fastapi import Response

    return Response(status_code=status.HTTP_204_NO_CONTENT)
