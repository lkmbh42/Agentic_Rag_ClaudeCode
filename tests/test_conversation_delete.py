"""Deleting a conversation: owner-only, and it takes its messages + feedback."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.chat import ChatMessage, ChatSession, MessageFeedback
from app.models.enums import MessageRole


def _conversation(sync_session, user_id):
    s = ChatSession(user_id=user_id, title="Q")
    sync_session.add(s)
    sync_session.flush()
    u = ChatMessage(session_id=s.id, role=MessageRole.USER, content="Frage?")
    a = ChatMessage(session_id=s.id, role=MessageRole.ASSISTANT, content="Antwort [1].")
    sync_session.add_all([u, a])
    sync_session.flush()
    sync_session.add(MessageFeedback(message_id=a.id, user_id=user_id, rating="up"))
    sync_session.commit()
    return s, a


async def test_owner_deletes_conversation_and_its_messages(client, login, seed, sync_session):
    s, a = _conversation(sync_session, seed["alice"]["id"])
    sid, aid = s.id, a.id  # keep plain ids; the ORM rows vanish on delete
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])

    assert (await client.delete(f"/chat/sessions/{sid}", headers=alice)).status_code == 204
    # Gone from the list and no longer openable.
    ids = [x["id"] for x in (await client.get("/chat/sessions", headers=alice)).json()]
    assert str(sid) not in ids
    assert (await client.get(f"/chat/sessions/{sid}", headers=alice)).status_code == 404

    # Cascade: messages and feedback removed too.
    sync_session.expire_all()
    assert sync_session.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == sid)) == 0
    assert sync_session.scalar(select(func.count()).select_from(MessageFeedback).where(MessageFeedback.message_id == aid)) == 0


async def test_cannot_delete_another_users_conversation(client, login, seed, sync_session):
    s, _ = _conversation(sync_session, seed["alice"]["id"])
    sid = s.id
    bob = await login(seed["bob"]["email"], seed["bob"]["password"])

    # 404, not 403 — never confirm someone else's conversation exists.
    assert (await client.delete(f"/chat/sessions/{sid}", headers=bob)).status_code == 404
    assert (await client.delete(f"/chat/sessions/{uuid.uuid4()}", headers=bob)).status_code == 404
    # Still there for its owner.
    sync_session.expire_all()
    assert sync_session.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.id == sid)) == 1
