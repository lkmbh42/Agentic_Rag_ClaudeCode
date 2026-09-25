"""Knowledge-gap analytics: which questions the RAG could not answer well.

A question counts as a gap when its answer
  - is the graph's abstention (INSUFFICIENT_ANSWER) or empty  -> "no_evidence"
  - is the model stating the documents don't contain it        -> "declined"
  - received a thumbs-down from the asker                      -> "negative_feedback"
(an answer can carry more than one kind).

Repeats are grouped by a normalized form of the question so the report shows
what is asked often and missing — i.e. which documents to add. Only the NUMBER
of distinct askers is exposed, never who asked: this is content-gap analytics
for admins, not user tracking.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.state import INSUFFICIENT_ANSWER
from app.models.chat import ChatMessage, ChatSession, MessageFeedback
from app.models.enums import MessageRole

NO_EVIDENCE = "no_evidence"
DECLINED = "declined"
NEGATIVE_FEEDBACK = "negative_feedback"
_KIND_ORDER = (NO_EVIDENCE, DECLINED, NEGATIVE_FEEDBACK)

# Phrases the generator uses when the retrieved context lacks the answer. Only
# the head of the answer is checked: a refusal opens the answer, whereas the same
# words deep inside a real answer ("…for 2021 there are no figures") are not a gap.
# Tuned against the real chat history (a scan of unflagged answers surfaced the
# "nicht direkt…", "es fehlt ein…", "does not specify", "no answer can be…"
# phrasings). Kept specific: bare "nicht"/"keine" would flag real answers such
# as "Split-Tunneling ist deaktiviert und darf nicht umgangen werden".
_DECLINE_MARKERS = (
    # German
    "enthält keine", "enthält keinen", "enthalten keine", "enthält nicht",
    "keine angaben", "keine information", "keinen hinweis", "keine hinweise",
    "nicht enthalten", "nicht beantworten", "nicht beantwortet", "liegen keine",
    "keine daten", "keine relevanten", "keine spezifische", "keine konkrete",
    "nicht direkt in den", "nicht direkt aus den", "kann nicht direkt",
    "nicht abgeleitet", "nicht nachvollzie", "es fehlt ein", "es fehlen",
    "keine antwort", "keine genauen", "kann ich keine", "steht nicht in",
    "nicht in den gegebenen", "nicht in den genannten", "nicht im angegebenen",
    "nicht im gegebenen", "nicht im kontext", "nicht erwähnt", "nicht direkt belegt",
    "beantwortbar", "beziehen sich nicht auf", "bezieht sich nicht auf",
    # English
    "does not contain", "do not contain", "doesn't contain", "don't contain",
    "no information", "no specific information", "cannot be answered",
    "can't be answered", "not mention", "no answer can be", "no relevant",
    "not provided in", "does not specify", "do not specify", "not specified in",
    "there is no mention", "there is no specific", "not available in the",
    "not in the provided",
)
_HEAD_CHARS = 240

_MAX_MESSAGES = 20_000   # hard cap on rows scanned per report
_SAMPLE_CHARS = 400
_MAX_REASONS = 5


def classify_answer(answer: str | None) -> str | None:
    """The gap kind of an answer by its text alone, or None if it answered."""
    text = (answer or "").strip()
    if not text or text == INSUFFICIENT_ANSWER:
        return NO_EVIDENCE
    head = text[:_HEAD_CHARS].lower()
    if any(marker in head for marker in _DECLINE_MARKERS):
        return DECLINED
    return None


def normalize_question(question: str) -> str:
    """Grouping key: case-, whitespace- and trailing-punctuation-insensitive."""
    q = re.sub(r"\s+", " ", question.lower()).strip()
    return q.strip(" ?!.,;:\"'„“”")


@dataclass
class _Group:
    question: str
    last_asked: datetime
    sample_answer: str
    count: int = 0
    users: set[uuid.UUID] = field(default_factory=set)
    kinds: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)


async def build_report(db: AsyncSession, days: int = 30, limit: int = 200) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await db.execute(
        select(ChatMessage.id, ChatMessage.session_id, ChatMessage.role,
               ChatMessage.content, ChatMessage.created_at, ChatSession.user_id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.created_at >= since)
        # created_at defaults to Postgres now() = transaction start, so a question
        # and its answer written in one transaction tie; the question goes first.
        .order_by(ChatMessage.session_id, ChatMessage.created_at,
                  case((ChatMessage.role == MessageRole.USER, 0), else_=1))
        .limit(_MAX_MESSAGES)
    )).all()

    # Pair each assistant answer with the user question right before it.
    pairs: list[tuple] = []  # (question, answer_id, answer, asked_at, user_id)
    last_question: dict[uuid.UUID, str] = {}
    for mid, sid, role, content, created_at, user_id in rows:
        if role == MessageRole.USER:
            last_question[sid] = content
        elif role == MessageRole.ASSISTANT and sid in last_question:
            pairs.append((last_question.pop(sid), mid, content, created_at, user_id))

    # Thumbs-down (with optional reasons) on those answers.
    downs: dict[uuid.UUID, list[str]] = {}
    answer_ids = [p[1] for p in pairs]
    if answer_ids:
        fb = (await db.execute(
            select(MessageFeedback.message_id, MessageFeedback.reason)
            .where(MessageFeedback.message_id.in_(answer_ids),
                   MessageFeedback.rating == "down")
        )).all()
        for message_id, reason in fb:
            downs.setdefault(message_id, [])
            if reason and reason.strip():
                downs[message_id].append(reason.strip())

    groups: dict[str, _Group] = {}
    gap_questions = negative = 0
    for question, answer_id, answer, asked_at, user_id in pairs:
        kinds: set[str] = set()
        if (kind := classify_answer(answer)) is not None:
            kinds.add(kind)
        if answer_id in downs:
            kinds.add(NEGATIVE_FEEDBACK)
            negative += 1
        if not kinds:
            continue
        gap_questions += 1
        key = normalize_question(question)
        g = groups.get(key)
        if g is None:
            g = groups[key] = _Group(question=question, last_asked=asked_at,
                                     sample_answer=answer or "")
        elif asked_at >= g.last_asked:  # show the latest phrasing + answer
            g.question, g.last_asked, g.sample_answer = question, asked_at, answer or ""
        g.count += 1
        g.users.add(user_id)
        g.kinds |= kinds
        for r in downs.get(answer_id, []):
            if r not in g.reasons and len(g.reasons) < _MAX_REASONS:
                g.reasons.append(r)

    items = sorted(groups.values(), key=lambda g: (-g.count, -g.last_asked.timestamp()))
    total = len(pairs)
    return {
        "window_days": days,
        "total_questions": total,
        "gap_questions": gap_questions,
        "gap_rate": round(gap_questions / total, 4) if total else 0.0,
        "negative_feedback": negative,
        "items": [
            {
                "question": g.question,
                "count": g.count,
                "users": len(g.users),
                "last_asked": g.last_asked,
                "kinds": [k for k in _KIND_ORDER if k in g.kinds],
                "sample_answer": g.sample_answer[:_SAMPLE_CHARS],
                "feedback_reasons": g.reasons,
            }
            for g in items[:limit]
        ],
    }
