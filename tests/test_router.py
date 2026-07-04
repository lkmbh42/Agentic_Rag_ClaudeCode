"""Intent router tests (Phase 3).

Fast tests exercise the deterministic shell (schema validation, fallback,
labeled-set integrity) with stub LLMs — no model required. The accuracy gate
(CLAUDE.md Phase 3 DoD: >=90% on a labeled set of >=60 queries) runs the REAL
classification model over eval/router_labeled.jsonl and is marked `llm`, like
the `docling` tests: it needs the compose network. p95 latency is asserted only
against vLLM (prod serving); the CPU dev model is exempt from latency targets
(accepted Phase 1 hardware exception) but the measurement is always printed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.router import FALLBACK_INTENT, INTENTS, IntentRouter

LABELED = Path(__file__).resolve().parents[1] / "eval" / "router_labeled.jsonl"


def load_labeled() -> list[dict]:
    rows = []
    for line in LABELED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


class StubLLM:
    def __init__(self, intent=None, exc=None):
        self._intent, self._exc = intent, exc
        self.calls = 0

    def route_intent(self, query):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._intent


# ------------------------------------------------------- deterministic shell
def test_valid_intent_passes_through():
    for intent in INTENTS:
        decision = IntentRouter(llm=StubLLM(intent=intent)).classify("Frage?")
        assert decision.intent == intent
        assert decision.source == "llm"
        assert decision.latency_ms >= 0


def test_unknown_label_falls_back_to_text():
    decision = IntentRouter(llm=StubLLM(intent="banana")).classify("Frage?")
    assert decision.intent == FALLBACK_INTENT
    assert decision.source == "fallback"


def test_none_from_model_falls_back():
    decision = IntentRouter(llm=StubLLM(intent=None)).classify("Frage?")
    assert decision.intent == FALLBACK_INTENT
    assert decision.source == "fallback"


def test_model_exception_falls_back():
    decision = IntentRouter(llm=StubLLM(exc=RuntimeError("backend down"))).classify("Frage?")
    assert decision.intent == FALLBACK_INTENT
    assert decision.source == "fallback"


def test_empty_query_short_circuits_without_llm_call():
    stub = StubLLM(intent="visual")
    decision = IntentRouter(llm=stub).classify("   ")
    assert decision.intent == FALLBACK_INTENT
    assert stub.calls == 0


# ---------------------------------------------------------- labeled set shape
def test_labeled_set_integrity():
    rows = load_labeled()
    assert len(rows) >= 60, "Phase 3 DoD requires a labeled set of >=60 queries"
    assert {r["intent"] for r in rows} == set(INTENTS), "every intent must be covered"
    assert {r["lang"] for r in rows} >= {"de", "en"}, "Rule 8: DE + EN coverage"
    assert len({r["id"] for r in rows}) == len(rows), "ids must be unique"
    for intent in INTENTS:
        n = sum(1 for r in rows if r["intent"] == intent)
        assert n >= 10, f"intent {intent!r} is under-represented ({n} < 10)"


# ------------------------------------------------------------- accuracy gate
@pytest.mark.llm
def test_router_accuracy_on_labeled_set():
    settings = get_settings()
    rows = load_labeled()
    router = IntentRouter()

    misses: list[tuple[str, str, str]] = []
    latencies: list[float] = []
    for row in rows:
        decision = router.classify(row["query"])
        latencies.append(decision.latency_ms)
        if decision.intent != row["intent"]:
            misses.append((row["id"], row["intent"], decision.intent))

    accuracy = 1 - len(misses) / len(rows)
    latencies.sort()
    p95 = latencies[int(round(0.95 * (len(latencies) - 1)))]
    print(f"\nrouter accuracy: {accuracy:.1%} ({len(rows) - len(misses)}/{len(rows)}), "
          f"p95 latency: {p95:.0f}ms, misses: {misses}")

    assert accuracy >= 0.90, f"router accuracy {accuracy:.1%} < 90% — misses: {misses}"
    if settings.llm_backend == "vllm":  # latency DoD applies to prod serving only
        assert p95 <= 400, f"p95 router latency {p95:.0f}ms > 400ms on vLLM"
