"""Offline golden-set regression.

A versioned Q&A set, run through the SAME agent graph used in production, gated on
expectations. Distinct from live-traffic eval: this is what you run in CI before
shipping a prompt/model/config change. Pass/fail per case; the suite is green only
if every case passes.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.config import get_settings

_settings = get_settings()


@dataclass
class CaseResult:
    id: str
    passed: bool
    reason: str
    answer: str


@dataclass
class GoldenReport:
    results: list[CaseResult]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def green(self) -> bool:
        return self.passed == self.total and self.total > 0

    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]


def load_cases(path: str) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                cases.append(json.loads(line))
    return cases


def run_case(graph, case: dict, allowed_collection_ids: set[uuid.UUID]) -> CaseResult:
    config = {"configurable": {"thread_id": str(uuid.uuid4())},
              "recursion_limit": _settings.max_graph_iterations * 3 + 10}
    state = graph.invoke({
        "messages": [{"role": "user", "content": case["query"]}],
        "query": case["query"],
        "allowed_collection_ids": [str(c) for c in allowed_collection_ids],
        "iterations": 0, "retrieval_retries": 0, "generation_retries": 0,
    }, config)
    answer = state.get("answer", "")
    insufficient = state.get("insufficient", False)

    if case.get("expect_insufficient"):
        ok = bool(insufficient)
        return CaseResult(case["id"], ok, "" if ok else "expected insufficient", answer)

    lower = answer.lower()
    missing = [s for s in case.get("expect_contains", []) if s.lower() not in lower]
    if missing:
        return CaseResult(case["id"], False, f"missing {missing}", answer)
    if case.get("expect_citation") and not state.get("citations"):
        return CaseResult(case["id"], False, "expected a citation", answer)
    return CaseResult(case["id"], True, "", answer)


def run_golden(graph, cases: list[dict], allowed_collection_ids: set[uuid.UUID]) -> GoldenReport:
    return GoldenReport([run_case(graph, c, allowed_collection_ids) for c in cases])
