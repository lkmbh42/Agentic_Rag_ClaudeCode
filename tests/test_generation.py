"""Generation DoD: an unanswerable question returns the safe insufficient-evidence
answer with NO fabricated citations. Plus citation extraction + SSE streaming."""

from __future__ import annotations

import uuid

from app.graph.builder import build_graph
from app.graph.checkpointer import build_checkpointer
from app.graph.citations import extract_citations
from app.graph.state import INSUFFICIENT_ANSWER
from tests.fakes import FakeCache, FakeLLM, FakeRedis, FakeRetriever

_CHUNKS = [
    {"document_id": "d1", "chunk_id": "c1", "page_number": 1, "chunk_type": "text"},
    {"document_id": "d2", "chunk_id": "c2", "page_number": 2, "chunk_type": "table"},
]


def test_citations_only_referenced_markers():
    cites = extract_citations("The policy allows three days [1].", _CHUNKS)
    assert [c["marker"] for c in cites] == [1]
    assert cites[0]["document_id"] == "d1"


def test_citations_drop_out_of_range_no_fabrication():
    assert extract_citations("See source [9].", _CHUNKS) == []
    assert extract_citations("No citation here.", _CHUNKS) == []


def test_insufficient_answer_has_no_citations():
    assert extract_citations(INSUFFICIENT_ANSWER, _CHUNKS) == []


def _run(llm, conninfo, cache=None):
    coll = uuid.uuid4()
    graph = build_graph(llm, checkpointer=build_checkpointer(conninfo, max_size=2),
                        retriever=FakeRetriever(), cache=cache or FakeCache(),
                        redis_client=FakeRedis())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 80}
    initial = {"messages": [{"role": "user", "content": "q"}], "query": "q",
               "allowed_collection_ids": [str(coll)],
               "iterations": 0, "retrieval_retries": 0, "generation_retries": 0}
    return graph, initial, config


def test_unanswerable_returns_safe_answer_no_citations(checkpointer_conninfo):
    graph, initial, config = _run(
        FakeLLM(relevant=False, grounded=False), checkpointer_conninfo)
    result = graph.invoke(initial, config)
    assert result["insufficient"] is True
    assert result["answer"] == INSUFFICIENT_ANSWER
    assert result["citations"] == []  # no fabricated citations


def test_grounded_answer_cites_referenced_chunk(checkpointer_conninfo):
    graph, initial, config = _run(
        FakeLLM(answer="Three days per week [1].", relevant=True, grounded=True),
        checkpointer_conninfo)
    result = graph.invoke(initial, config)
    assert result["answer"] == "Three days per week [1]."
    assert len(result["citations"]) == 1
    assert result["citations"][0]["marker"] == 1


def test_streaming_emits_generator_tokens(checkpointer_conninfo):
    graph, initial, config = _run(
        FakeLLM(answer="The policy allows three days [1].", relevant=True, grounded=True),
        checkpointer_conninfo)
    tokens, final = [], {}
    for mode, data in graph.stream(initial, config, stream_mode=["custom", "values"]):
        if mode == "custom":
            tokens.append(data)
        elif mode == "values":
            final = data
    assert tokens, "expected streamed tokens"
    assert "policy" in "".join(tokens)
    assert final["answer"] == "The policy allows three days [1]."
