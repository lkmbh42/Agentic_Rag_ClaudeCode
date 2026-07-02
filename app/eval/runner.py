"""Persist eval scores (worker side) + a default judge chat_fn bound to the LLM."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.eval.judge import EvalScores, evaluate
from app.models.eval import EvalResult


def default_chat_fn():
    """A chat_fn(system, user)->str backed by the configured LLM (Ollama/vLLM)."""
    from app.graph.llm import OpenAILLM

    llm = OpenAILLM()
    return lambda system, user: llm._chat(system, user, max_tokens=16)


def score_payload(chat_fn, payload: dict) -> EvalScores:
    return evaluate(chat_fn, payload)


def persist_eval(db: Session, payload: dict, scores: EvalScores) -> EvalResult:
    row = EvalResult(
        request_id=uuid.UUID(payload["request_id"]) if payload.get("request_id") else uuid.uuid4(),
        query=payload.get("query", ""),
        answer=payload.get("answer", ""),
        route=payload.get("route"),
        cache_hit=bool(payload.get("cache_hit", False)),
        **scores.as_dict(),
    )
    db.add(row)
    db.commit()
    return row
