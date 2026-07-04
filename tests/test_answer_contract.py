"""Phase 4 answer-contract tests.

The DoD requires the chart-value read-vs-estimated qualifier and the refusal
behavior to be part of the PROMPT CONTRACT — these tests pin the contract
clauses (DE + EN) and the multimodal message wiring so a prompt regression
fails CI, independent of model quality (which the GPU-host eval measures).
"""

from __future__ import annotations

import uuid

from app.config import get_settings
from app.graph import prompts
from app.graph.builder import build_graph
from app.llm.client import OpenAILLM
from tests.fakes import FakeCache, FakeLLM, FakeRedis, FakeRetriever, FakeVisualRetriever

_settings = get_settings()


# ------------------------------------------------------------ prompt contract
def test_contract_clauses_present_in_both_languages():
    en, de = prompts.GENERATOR_SYSTEM, prompts.GENERATOR_SYSTEM_DE
    # citation protocol
    assert "[1]" in en and "[1]" in de
    # context-only + no outside documents
    assert "ONLY the numbered context" in en
    assert "AUSSCHLIESSLICH" in de
    assert "never reference documents" in en
    assert "nie auf Dokumente außerhalb" in de
    # chart-value qualifier (read vs estimated)
    assert "read" in en and "visually estimated" in en
    assert "abgelesen" in de and "visuell geschätzt" in de
    # ADR honesty rule for uninterpreted figures
    assert "not interpreted" in en
    assert "nicht interpretiert" in de
    # refusal escape hatch
    assert "lacks the answer" in en
    assert "nicht enthält" in de


def test_language_routing_picks_matching_contract():
    assert prompts.generator_system("Wie viele Urlaubstage stehen mir zu?") \
        == prompts.GENERATOR_SYSTEM_DE
    assert prompts.generator_system("How many vacation days do I get?") \
        == prompts.GENERATOR_SYSTEM


# --------------------------------------------------------- multimodal wiring
def test_user_content_plain_without_images():
    assert OpenAILLM._user_content("hello", None) == "hello"
    assert OpenAILLM._user_content("hello", []) == "hello"


def test_user_content_parts_with_images():
    parts = OpenAILLM._user_content("frage", ["QUJD", "REVG"])
    assert parts[0] == {"type": "text", "text": "frage"}
    assert [p["type"] for p in parts[1:]] == ["image_url", "image_url"]
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"


def _run_graph(llm, visual, monkeypatch, multimodal, coll=None):
    monkeypatch.setattr(_settings, "llm_multimodal", multimodal)
    graph = build_graph(llm, retriever=FakeRetriever(), cache=FakeCache(),
                        redis_client=FakeRedis(), visual_retriever=visual)
    return graph.invoke({
        "messages": [{"role": "user", "content": "Was zeigt das Diagramm?"}],
        "query": "Was zeigt das Diagramm?",
        "allowed_collection_ids": [str(coll or uuid.uuid4())],
        "iterations": 0, "retrieval_retries": 0, "generation_retries": 0,
    })


def test_generator_receives_no_images_when_text_only(monkeypatch):
    llm = FakeLLM(intent="visual")
    _run_graph(llm, FakeVisualRetriever(), monkeypatch, multimodal=False)
    assert llm.last_images == []


def test_generator_receives_images_when_multimodal(monkeypatch):
    from app.retrieval.visual import RetrievedPage

    coll, doc = uuid.uuid4(), uuid.uuid4()
    page = RetrievedPage(point_id=uuid.uuid4(), document_id=doc,
                         collection_id=coll, page_number=1,
                         image_uri=f"s3://pages/{doc}/1.png",
                         file_name="chart.pdf", score=0.9)

    class Store:  # MinIO stand-in: the assembler resolves s3:// through it
        def get(self, uri):
            return b"png-bytes"

    import app.ingestion.object_store as objstore

    monkeypatch.setattr(objstore, "get_object_store", lambda: Store())

    llm = FakeLLM(intent="visual")
    result = _run_graph(llm, FakeVisualRetriever(pages=[page]), monkeypatch,
                        multimodal=True, coll=coll)
    assert len(llm.last_images) == 1, "the VL generate call must carry the page image"
    assert result["context_images"] == 1