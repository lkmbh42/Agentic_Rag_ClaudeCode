"""Unit tests for the deterministic scoring logic in eval/run_eval.py.

No backend, no LLM — pure functions only. Run: python -m pytest eval/test_run_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run_eval import (  # noqa: E402
    case_passed,
    citation_ok,
    contains_pass,
    filter_subset,
    hit_at_k,
    is_insufficient,
    load_cases,
    page_hit_at_k,
)

GOLDEN = Path(__file__).parent / "golden_v2.jsonl"


# ---------------------------------------------------------------- golden set

def test_golden_v2_loads_130_cases():
    cases = load_cases(GOLDEN)
    assert len(cases) == 130
    assert len({c["id"] for c in cases}) == 130


def test_golden_v2_split_100_text_30_visual():
    cases = load_cases(GOLDEN)
    assert len(filter_subset(cases, "text")) == 100
    assert len(filter_subset(cases, "visual")) == 30
    assert len(filter_subset(cases, "all")) == 130


def test_golden_v2_schema_complete():
    required = {"id", "lang", "modality", "query", "expected_answer",
                "expect_contains", "expect_citation", "expect_insufficient",
                "source", "retrieval_targets"}
    for c in load_cases(GOLDEN):
        assert required <= set(c), c.get("id")
        if not c["expect_insufficient"]:
            assert c["source"] is not None and c["retrieval_targets"], c["id"]
        else:
            assert c["retrieval_targets"] == [], c["id"]


def test_load_cases_skips_comments(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text('# comment\n\n{"id":"x"}\n', encoding="utf-8")
    assert load_cases(p) == [{"id": "x"}]


# ------------------------------------------------------------- insufficiency

def test_insufficient_via_flag():
    assert is_insufficient("Some answer.", True)


def test_insufficient_via_marker_en_and_de():
    assert is_insufficient("Insufficient evidence to answer.", False)
    assert is_insufficient("Es liegen nicht genügend Belege vor.", False)


def test_insufficient_empty_answer():
    assert is_insufficient("", False)
    assert is_insufficient("   ", False)


def test_sufficient_answer_not_flagged():
    assert not is_insufficient("Die Frist beträgt 30 Tage [1].", False)


# ------------------------------------------------------------ contains check

def test_contains_case_insensitive_and_conjunctive():
    assert contains_pass("Der Manager ist KeePassXC [1].", ["keepassxc"])
    assert contains_pass("A und B", ["a", "b"])
    assert not contains_pass("nur A", ["a", "b"])


def test_contains_empty_list_always_passes():
    assert contains_pass("anything", [])


# ----------------------------------------------------------------- hit@k

def test_hit_at_k_respects_rank():
    ids = ["d1", "d2", "d3", "d4", "d5"]
    assert hit_at_k(ids, {"d1"}, 1)
    assert not hit_at_k(ids, {"d3"}, 1)
    assert hit_at_k(ids, {"d3"}, 3)
    assert hit_at_k(ids, {"d5"}, 5)
    assert not hit_at_k(ids, {"d9"}, 5)


def test_page_hit_requires_page_match_when_pages_given():
    doc_by_file = {"a.pdf": "d1"}
    targets = [{"file": "a.pdf", "pages": [3]}]
    hit = [{"document_id": "d1", "page_number": 3}]
    miss = [{"document_id": "d1", "page_number": 4}]
    assert page_hit_at_k(hit, targets, doc_by_file, 5)
    assert not page_hit_at_k(miss, targets, doc_by_file, 5)


def test_page_hit_falls_back_to_doc_match_without_pages():
    doc_by_file = {"a.docx": "d1"}
    targets = [{"file": "a.docx", "pages": []}]
    rows = [{"document_id": "d1", "page_number": None}]
    assert page_hit_at_k(rows, targets, doc_by_file, 5)


# --------------------------------------------------------------- citations

def test_citation_ok_matches_target_doc():
    assert citation_ok([{"document_id": "d1"}], {"d1"})
    assert not citation_ok([{"document_id": "d2"}], {"d1"})
    assert not citation_ok([], {"d1"})


# ------------------------------------------------------------- pass/fail

def _case(**over):
    base = {"expect_insufficient": False, "expect_citation": True,
            "expect_contains": ["x"]}
    base.update(over)
    return base


def _row(**over):
    base = {"insufficient": False, "contains_pass": True,
            "citations_present": True}
    base.update(over)
    return base


def test_pass_normal_case():
    assert case_passed(_case(), _row())


def test_fail_when_contains_missing():
    assert not case_passed(_case(), _row(contains_pass=False))


def test_fail_when_citation_expected_but_absent():
    assert not case_passed(_case(), _row(citations_present=False))


def test_fail_when_unexpectedly_insufficient():
    assert not case_passed(_case(), _row(insufficient=True))


def test_insufficient_expected_passes_only_on_refusal():
    case = _case(expect_insufficient=True, expect_citation=False, expect_contains=[])
    assert case_passed(case, _row(insufficient=True, citations_present=False))
    assert not case_passed(case, _row(insufficient=False))


def test_citation_not_required_when_not_expected():
    case = _case(expect_citation=False)
    assert case_passed(case, _row(citations_present=False))


# ------------------------------------------------- golden/report consistency

def test_every_target_file_exists_in_fixture_corpus():
    corpus = Path(__file__).parent / "fixtures" / "corpus"
    have = {p.name for p in corpus.iterdir()} if corpus.exists() else set()
    want = {t["file"] for c in load_cases(GOLDEN) for t in c["retrieval_targets"]}
    assert want <= have, f"missing fixtures: {sorted(want - have)}"


def test_golden_is_valid_jsonl_roundtrip():
    for c in load_cases(GOLDEN):
        json.dumps(c)  # every case must be JSON-serializable as-is
