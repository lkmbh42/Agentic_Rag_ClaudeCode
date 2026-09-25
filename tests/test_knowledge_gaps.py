"""Knowledge-gap analytics: classification, grouping, aggregation, admin-only."""

from __future__ import annotations

import pytest

from app.graph.state import INSUFFICIENT_ANSWER
from app.models.chat import ChatMessage, ChatSession, MessageFeedback
from app.models.enums import MessageRole
from app.services.knowledge_gaps import (
    DECLINED,
    NEGATIVE_FEEDBACK,
    NO_EVIDENCE,
    classify_answer,
    normalize_question,
)

# ------------------------------------------------------------------ unit


@pytest.mark.parametrize("answer, expected", [
    (INSUFFICIENT_ANSWER, NO_EVIDENCE),
    ("", NO_EVIDENCE),
    ("Der Kontext enthält keine Angaben zur Adresse des Kreisjobcenters [5].", DECLINED),
    ("Der bereitgestellte Kontext enthält keine Information darüber.", DECLINED),
    ("The provided context does not contain information about that.", DECLINED),
    # Real refusal phrasings seen in production chat history:
    ("Die Fragestellung ist nicht direkt in den gegebenen Kontext enthalten.", DECLINED),
    ("Die gegebenen Kontexte beziehen sich nicht auf eine Probezeit.", DECLINED),
    ("Die Frage ist nicht mit dem vorliegenden Kontext beantwortbar.", DECLINED),
    ("Die Höhe des Weihnachtsgeldes wird im Kontext nicht erwähnt. [1]", DECLINED),
    ("[1] and [2] do not mention any specific password manager.", DECLINED),
    ("The probation period is not specified in any of the provided sections.", DECLINED),
    ("The information is not available in the provided contexts. [1]", DECLINED),
    # Real answers that merely contain a negation — must NOT be flagged:
    ("Marburg hat 77 410 Einwohner [1].", None),
    ("Split-Tunneling ist deaktiviert und darf nicht umgangen werden [1].", None),
    ("Confidential documents must not be shared outside the organization [1], [2].", None),
    ("Split-Tunneling is deactivated and cannot be bypassed [1].", None),
])
def test_classify_answer(answer, expected):
    assert classify_answer(answer) == expected


def test_decline_phrase_deep_in_a_real_answer_is_not_a_gap():
    answer = "Marburg hat 77 410 Einwohner [1]. " + "Details folgen. " * 20 + \
        "Für 2021 liegen keine Daten vor."
    assert classify_answer(answer) is None


def test_normalize_question_groups_trivial_variants():
    assert normalize_question("Wie viele Einwohner?") == \
        normalize_question("  wie viele   einwohner ")


# ------------------------------------------------------------ integration


def _qa(sync_session, user_id, question, answer):
    s = ChatSession(user_id=user_id, title=question)
    sync_session.add(s)
    sync_session.flush()
    q = ChatMessage(session_id=s.id, role=MessageRole.USER, content=question)
    sync_session.add(q)
    sync_session.flush()  # the question must precede the answer in time
    a = ChatMessage(session_id=s.id, role=MessageRole.ASSISTANT, content=answer)
    sync_session.add(a)
    sync_session.flush()
    return a


@pytest.fixture
def gap_data(seed, sync_session):
    alice, bob = seed["alice"]["id"], seed["bob"]["id"]
    declined = "Der Kontext enthält keine Angaben dazu."
    # Same missing topic asked 3x by 2 users, phrased slightly differently.
    _qa(sync_session, alice, "Wo ist das Jobcenter?", declined)
    _qa(sync_session, alice, "wo ist das jobcenter", declined)
    _qa(sync_session, bob, "Wo ist das Jobcenter?", INSUFFICIENT_ANSWER)
    # Answered fine -> not a gap.
    _qa(sync_session, alice, "Wie viele Einwohner hat Marburg?", "77 410 [1].")
    # Answered, but the asker disagreed -> gap via feedback, reason surfaced.
    bad = _qa(sync_session, bob, "Wann ist der Hessentag?", "Im Mai [1].")
    sync_session.add(MessageFeedback(message_id=bad.id, user_id=bob,
                                     rating="down", reason="falsch, im Juni"))
    sync_session.commit()


async def test_knowledge_gap_report_aggregates(client, login, seed, gap_data):
    admin = await login(seed["admin"]["email"], seed["admin"]["password"])
    r = await client.get("/admin/knowledge-gaps?days=30", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_questions"] == 5
    assert body["gap_questions"] == 4
    assert body["negative_feedback"] == 1
    assert body["gap_rate"] == 0.8

    items = body["items"]
    assert len(items) == 2
    top = items[0]  # most frequent first
    assert normalize_question(top["question"]) == "wo ist das jobcenter"
    assert top["count"] == 3 and top["users"] == 2
    assert top["kinds"] == [NO_EVIDENCE, DECLINED]

    fb = items[1]
    assert fb["kinds"] == [NEGATIVE_FEEDBACK]
    assert fb["feedback_reasons"] == ["falsch, im Juni"]

    # Privacy: counts only, no asker identities anywhere in the payload.
    for uid in (seed["alice"]["id"], seed["bob"]["id"]):
        assert str(uid) not in r.text
    assert "alice@" not in r.text and "bob@" not in r.text


async def test_knowledge_gaps_admin_only(client, login, seed):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    r = await client.get("/admin/knowledge-gaps", headers=alice)
    assert r.status_code == 403


async def test_knowledge_gaps_rejects_bad_window(client, login, seed):
    admin = await login(seed["admin"]["email"], seed["admin"]["password"])
    r = await client.get("/admin/knowledge-gaps?days=0", headers=admin)
    assert r.status_code == 422
