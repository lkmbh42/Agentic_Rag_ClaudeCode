"""Reopened conversations keep their sources — but only for documents the user
can still read (citations store verbatim passages; access can be revoked)."""

from __future__ import annotations

import uuid

from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.enums import DocumentStatus, MessageRole


def _doc(sync_session, collection_id, name):
    d = Document(collection_id=collection_id, filename=name, file_type="pdf",
                 content_hash=uuid.uuid4().hex, status=DocumentStatus.INDEXED)
    sync_session.add(d)
    sync_session.flush()
    return d


async def test_history_keeps_citations_and_hides_unreadable(client, login, seed, sync_session):
    readable = _doc(sync_session, seed["coll_a"], "own-dept.pdf")      # alice: dept_a
    foreign = _doc(sync_session, seed["coll_b"], "other-dept.pdf")     # dept_b only

    s = ChatSession(user_id=seed["alice"]["id"], title="Q")
    sync_session.add(s)
    sync_session.flush()
    sync_session.add(ChatMessage(session_id=s.id, role=MessageRole.USER, content="Frage?"))
    sync_session.flush()
    sync_session.add(ChatMessage(
        session_id=s.id, role=MessageRole.ASSISTANT, content="Antwort [1] [2].",
        citations=[
            {"marker": 1, "document_id": str(readable.id), "page_number": 3,
             "file_name": "own-dept.pdf", "content": "visible passage"},
            {"marker": 2, "document_id": str(foreign.id), "page_number": 1,
             "file_name": "other-dept.pdf", "content": "SECRET passage",
             "image_uri": f"s3://figures/{foreign.id}/p1-001.png"},
        ],
    ))
    sync_session.commit()

    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    r = await client.get(f"/chat/sessions/{s.id}", headers=alice)
    assert r.status_code == 200, r.text
    answer = [m for m in r.json()["messages"] if m["role"] == "assistant"][0]

    first, second = answer["citations"]
    assert first["content"] == "visible passage" and first["page_number"] == 3
    # Unreadable source: marker kept so "[2]" still resolves, everything else gone.
    assert second == {"marker": 2, "revoked": True}
    for leaked in ("SECRET", "other-dept.pdf", str(foreign.id)):
        assert leaked not in r.text

    user_msg = [m for m in r.json()["messages"] if m["role"] == "user"][0]
    assert user_msg["citations"] is None
