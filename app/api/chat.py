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
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import AuditAction, MessageRole
from app.models.user import User
from app.observability import metrics, tracing
from app.services.audit import record_audit
from app.schemas.chat import (
    ChatRequest,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionOut,
    ChatTurnResponse,
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
    db.add(ChatMessage(session_id=session.id, role=MessageRole.ASSISTANT, content=answer))
    await record_audit(
        db, action=AuditAction.GENERATION, user_id=user.id,
        resource_type="chat_session", resource_id=str(session.id),
        detail={"request_id": request_id, "route": result.get("route"),
                "cache_hit": result.get("cache_hit", False)},
    )
    await db.commit()

    # Observability (best-effort; never blocks the response).
    metrics.record_latency(total_ms)
    metrics.record_cache(bool(result.get("cache_hit", False)))
    tracing.record_request(result, total_ms, request_id, user.id)

    return ChatTurnResponse(
        session_id=session.id, answer=answer,
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
        db.add(ChatMessage(session_id=session_id, role=MessageRole.ASSISTANT, content=answer))
        await record_audit(
            db, action=AuditAction.GENERATION, user_id=user.id,
            resource_type="chat_session", resource_id=str(session_id),
            detail={"request_id": request_id, "route": final_state.get("route"),
                    "cache_hit": final_state.get("cache_hit", False), "streamed": True},
        )
        await db.commit()
        metrics.record_latency(total_ms)
        metrics.record_cache(bool(final_state.get("cache_hit", False)))
        tracing.record_request(final_state, total_ms, request_id, user.id)
        yield {"event": "done", "data": json.dumps({
            "session_id": str(session_id), "answer": answer,
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
    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        messages=messages,
    )
