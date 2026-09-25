"""Follow-up contextualization: only questions that depend on the previous
turn get it prepended; self-contained questions are searched as asked."""

from __future__ import annotations

import uuid

import pytest

from app.graph.nodes import Nodes, is_follow_up
from tests.fakes import FakeCache, FakeLLM, FakeRedis, FakeRetriever, FakeVisualRetriever


@pytest.mark.parametrize("q", [
    "und in Kirchhain?", "erklär mir mehr", "tell me more", "wie viele sind es?",
    "Was steht dazu im Dokument?", "what about the second one?", "Und die Adresse?",
])
def test_detects_follow_ups(q):
    assert is_follow_up(q)


@pytest.mark.parametrize("q", [
    "wie lautet die Adresse der Kreisjobcenter?",
    "Wer wählt den Landrat und wie lange ist die Amtszeit?",
    "Wie viele Einwohner hat Marburg laut der Tabelle?",
    "What is the annual revenue target for 2026?",
])
def test_self_contained_questions_are_not_follow_ups(q):
    assert not is_follow_up(q)


def _retrieve(question: str, previous: str) -> str:
    nodes = Nodes(FakeLLM(), retriever=FakeRetriever(), cache=FakeCache(),
                  redis_client=FakeRedis(), visual_retriever=FakeVisualRetriever(),
                  session_factory=object)
    state = {
        "query": question,
        "allowed_collection_ids": [str(uuid.uuid4())],
        "messages": [{"role": "user", "content": previous},
                     {"role": "assistant", "content": "…"},
                     {"role": "user", "content": question}],
    }
    return nodes.retriever_node(state)["chunks"][0]["content"]  # FakeRetriever echoes the query


def test_new_topic_is_searched_without_the_previous_question():
    used = _retrieve("wie lautet die Adresse der Kreisjobcenter?", "was ist der Tipp der Hessentag?")
    assert "Hessentag" not in used and "Kreisjobcenter" in used


def test_vague_follow_up_keeps_the_previous_topic():
    used = _retrieve("und in Kirchhain?", "Wie viele Einwohner hat Marburg?")
    assert "Einwohner hat Marburg" in used and "Kirchhain" in used
