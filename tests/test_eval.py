"""Eval DoD: LLM-as-judge scores persist to Postgres; golden set runs green."""

from __future__ import annotations

import uuid

from app.eval.golden import run_golden
from app.eval.judge import evaluate
from app.eval.runner import persist_eval
from app.graph.builder import build_graph
from app.graph.checkpointer import build_checkpointer
from app.models.eval import EvalResult
from tests.fakes import FakeCache, FakeLLM, FakeRedis, FakeRetriever


def _fake_chat(system, user):  # deterministic judge -> 8/10 = 0.8
    return "8"


def test_judge_scores_are_normalized_and_acl_checked():
    payload = {"query": "q", "answer": "answer [1].", "contexts": ["ctx"],
               "citations": [{"document_id": "d1"}], "retrieved_document_ids": ["d1"],
               "insufficient": False}
    s = evaluate(_fake_chat, payload)
    assert 0.0 <= s.faithfulness <= 1.0
    assert abs(s.faithfulness - 0.8) < 1e-9
    assert s.only_allowed_documents is True


def test_only_allowed_documents_false_on_out_of_scope_citation():
    payload = {"query": "q", "answer": "a [1].", "contexts": ["ctx"],
               "citations": [{"document_id": "dX"}], "retrieved_document_ids": ["d1"],
               "insufficient": False}
    assert evaluate(_fake_chat, payload).only_allowed_documents is False


def test_insufficient_answer_scores_safe():
    payload = {"query": "q", "answer": "", "contexts": [], "citations": [],
               "retrieved_document_ids": [], "insufficient": True}
    s = evaluate(_fake_chat, payload)
    assert s.faithfulness == 1.0 and s.citation_accuracy == 1.0


def test_persist_eval_writes_row(sync_session):
    payload = {"request_id": str(uuid.uuid4()), "query": "q", "answer": "a",
               "route": "simple_rag", "cache_hit": False, "contexts": [],
               "citations": [], "retrieved_document_ids": [], "insufficient": True}
    scores = evaluate(_fake_chat, payload)
    row = persist_eval(sync_session, payload, scores)
    fetched = sync_session.get(EvalResult, row.id)
    assert fetched is not None and fetched.only_allowed_documents is True


def _golden_graph(conninfo, llm):
    return build_graph(llm, checkpointer=build_checkpointer(conninfo, max_size=2),
                       retriever=FakeRetriever(), cache=FakeCache(),
                       redis_client=FakeRedis())


def test_golden_set_runs_green(checkpointer_conninfo):
    graph = _golden_graph(
        checkpointer_conninfo,
        FakeLLM(answer="The policy allows three days per week [1].", relevant=True, grounded=True))
    cases = [{"id": "remote", "query": "remote days",
              "expect_contains": ["three days"], "expect_citation": True}]
    report = run_golden(graph, cases, {uuid.uuid4()})
    assert report.green, report.failures()


def test_golden_set_catches_regression(checkpointer_conninfo):
    graph = _golden_graph(checkpointer_conninfo, FakeLLM(answer="Totally unrelated."))
    cases = [{"id": "remote", "query": "remote days", "expect_contains": ["three days"]}]
    report = run_golden(graph, cases, {uuid.uuid4()})
    assert not report.green and report.failures()
