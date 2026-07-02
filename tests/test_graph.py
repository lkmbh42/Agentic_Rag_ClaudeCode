"""Agent-graph DoD: multi-turn survives a 'restart' via the Postgres checkpointer,
and loops are provably bounded by circuit breakers."""

from __future__ import annotations

import uuid

import pytest

from app.config import get_settings
from app.graph.builder import _after_grade, _after_halluc, build_graph
from app.graph.checkpointer import build_checkpointer
from app.graph.state import INSUFFICIENT_ANSWER
from tests.fakes import FakeCache, FakeLLM, FakeRedis, FakeRetriever

_settings = get_settings()


def _build(llm, ckpt, cache=None):
    return build_graph(llm, checkpointer=ckpt, retriever=FakeRetriever(),
                       cache=cache or FakeCache(), redis_client=FakeRedis())


def _initial(message, coll):
    return {
        "messages": [{"role": "user", "content": message}],
        "query": message, "allowed_collection_ids": [str(coll)],
        "iterations": 0, "retrieval_retries": 0, "generation_retries": 0,
    }


def test_multi_turn_survives_restart(checkpointer_conninfo):
    coll = uuid.uuid4()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 80}

    ckpt1 = build_checkpointer(checkpointer_conninfo, max_size=2)
    graph1 = _build(FakeLLM(answer="First answer."), ckpt1)
    graph1.invoke(_initial("first question", coll), thread)

    # Simulate a restart: brand-new checkpointer + graph, same Postgres + thread.
    ckpt2 = build_checkpointer(checkpointer_conninfo, max_size=2)
    graph2 = _build(FakeLLM(answer="Second answer."), ckpt2)

    restored = graph2.get_state(thread)
    msgs = restored.values["messages"]
    assert any(m["content"] == "first question" for m in msgs)
    assert any(m["content"] == "First answer." for m in msgs)

    # Continue the conversation; history accumulates across the 'restart'.
    graph2.invoke(_initial("second question", coll), thread)
    msgs2 = graph2.get_state(thread).values["messages"]
    contents = [m["content"] for m in msgs2]
    assert "first question" in contents and "second question" in contents
    assert "First answer." in contents and "Second answer." in contents


def test_retrieval_retries_are_bounded(checkpointer_conninfo):
    coll = uuid.uuid4()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 80}
    ckpt = build_checkpointer(checkpointer_conninfo, max_size=2)
    # Always-irrelevant context -> rewrite/retry loop until the cap, then proceed.
    graph = _build(FakeLLM(relevant=False, grounded=True), ckpt)
    result = graph.invoke(_initial("q", coll), thread)
    assert result["retrieval_retries"] == _settings.max_retrieval_retries
    assert result.get("answer")  # still terminated with an answer


def test_pathological_query_terminates_insufficient(checkpointer_conninfo):
    coll = uuid.uuid4()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 80}
    ckpt = build_checkpointer(checkpointer_conninfo, max_size=2)
    # Never relevant, never grounded -> must still terminate safely.
    graph = _build(FakeLLM(relevant=False, grounded=False), ckpt)
    result = graph.invoke(_initial("q", coll), thread)
    assert result.get("insufficient") is True
    assert result["answer"] == INSUFFICIENT_ANSWER
    assert result["iterations"] <= _settings.max_graph_iterations + 5


def test_cache_hit_short_circuits(checkpointer_conninfo):
    from app.retrieval.semantic_cache import CacheHit

    coll = uuid.uuid4()
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 80}
    ckpt = build_checkpointer(checkpointer_conninfo, max_size=2)
    hit = CacheHit(answer="Cached.", query_text="q", score=1.0,
                   collection_ids=[str(coll)], document_ids=[str(uuid.uuid4())])
    graph = _build(FakeLLM(answer="should-not-be-used"), ckpt, cache=FakeCache(hit=hit))
    result = graph.invoke(_initial("q", coll), thread)
    assert result["cache_hit"] is True
    assert result["answer"] == "Cached."
    assert result.get("route") is None  # router never ran


def test_global_breaker_routes_to_insufficient():
    over = {"iterations": _settings.max_graph_iterations + 1, "relevance_ok": True}
    assert _after_grade(over) == "insufficient_answer"
    assert _after_halluc({**over, "grounded": True}) == "insufficient_answer"
