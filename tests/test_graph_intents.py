"""Phase 3 graph wiring: intent-routed retrieval paths.

All LLM behavior is faked; these tests prove the CONTROL FLOW — which nodes an
intent visits and what lands in state — not model quality (that's
test_router.py's accuracy gate and the GPU-host retrieval eval).
"""

from __future__ import annotations

import uuid

from app.graph.builder import build_graph
from app.retrieval.visual import RetrievedPage
from tests.fakes import FakeCache, FakeLLM, FakeRedis, FakeRetriever, FakeVisualRetriever


def _build(llm, visual=None, session_factory=None):
    return build_graph(
        llm, retriever=FakeRetriever(), cache=FakeCache(), redis_client=FakeRedis(),
        visual_retriever=visual or FakeVisualRetriever(),
        session_factory=session_factory,
    )


def _initial(message="q"):
    return {
        "messages": [{"role": "user", "content": message}],
        "query": message, "allowed_collection_ids": [str(uuid.uuid4())],
        "iterations": 0, "retrieval_retries": 0, "generation_retries": 0,
    }


def _page(score=0.9) -> RetrievedPage:
    doc = uuid.uuid4()
    return RetrievedPage(
        point_id=uuid.uuid4(), document_id=doc, collection_id=uuid.uuid4(),
        page_number=3, image_uri=f"s3://pages/{doc}/3.png",
        file_name="report.pdf", score=score,
    )


def test_text_intent_skips_visual_search():
    result = _build(FakeLLM(intent="text")).invoke(_initial())
    assert result["intent"] == "text"
    assert result["route"] == "text"  # API/audit surface follows the intent
    assert result["page_hits"] == []
    assert result.get("answer")


def test_visual_intent_collects_page_hits_alongside_text():
    page = _page()
    result = _build(FakeLLM(intent="visual"),
                    visual=FakeVisualRetriever(pages=[page])).invoke(_initial())
    assert result["intent"] == "visual"
    assert result["chunks"], "text-hybrid retrieval still runs (fusion)"
    assert len(result["page_hits"]) == 1
    hit = result["page_hits"][0]
    assert hit["image_uri"] == page.image_uri
    assert hit["page_number"] == 3
    assert result.get("answer")


def test_multi_doc_intent_routes_through_planner():
    result = _build(FakeLLM(intent="multi_doc")).invoke(_initial("compare all policies"))
    assert result["intent"] == "multi_doc"
    assert result["plan"] == ["compare all policies"], "planner must run"
    assert result.get("answer")


def test_metadata_intent_answers_from_lookup(monkeypatch):
    fake_chunks = [{
        "chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()),
        "collection_id": str(uuid.uuid4()), "chunk_type": "metadata",
        "page_number": None, "section_title": None,
        "content": "Dokument: a.pdf | Seiten: 3", "score": 1.0, "file_name": "a.pdf",
    }]
    import app.retrieval.metadata_lookup as ml

    monkeypatch.setattr(ml, "lookup_documents", lambda *a, **k: fake_chunks)

    class _S:  # session factory whose session is never actually used
        def __enter__(self): return self
        def __exit__(self, *a): return False

    result = _build(FakeLLM(intent="metadata"), session_factory=_S).invoke(_initial())
    assert result["intent"] == "metadata"
    assert result["chunks"] == fake_chunks
    # Deterministic lookup bypasses the rewrite loop entirely.
    assert result["retrieval_retries"] == 0
    assert result.get("answer")


def test_metadata_intent_falls_back_to_retrieval_when_no_hits(monkeypatch):
    import app.retrieval.metadata_lookup as ml

    monkeypatch.setattr(ml, "lookup_documents", lambda *a, **k: [])

    class _S:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    result = _build(FakeLLM(intent="metadata"), session_factory=_S).invoke(_initial())
    assert result["chunks"], "optional retrieval fallback must run"
    assert result["chunks"][0]["chunk_type"] == "text"
    assert result.get("answer")


def test_invalid_intent_from_model_falls_back_to_text():
    result = _build(FakeLLM(intent="chart_question")).invoke(_initial())
    assert result["intent"] == "text"
    assert result["intent_source"] == "fallback"
    assert result.get("answer")


def test_router_latency_is_recorded():
    result = _build(FakeLLM(intent="text")).invoke(_initial())
    assert result["router_latency_ms"] >= 0
