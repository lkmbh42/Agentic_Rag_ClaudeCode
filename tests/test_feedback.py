"""Phase 4 feedback: 👍/👎 + reason persisted per (message, user), ownership-
enforced like every session-scoped endpoint."""

from __future__ import annotations

import uuid

import pytest

from app.models.chat import ChatMessage, ChatSession
from app.models.enums import MessageRole


@pytest.fixture
def alice_conversation(seed, sync_session):
    """A session owned by alice with one user + one assistant message."""
    session = ChatSession(user_id=seed["alice"]["id"], title="Q")
    sync_session.add(session)
    sync_session.flush()
    user_msg = ChatMessage(session_id=session.id, role=MessageRole.USER, content="Frage?")
    bot_msg = ChatMessage(session_id=session.id, role=MessageRole.ASSISTANT, content="Antwort [1].")
    sync_session.add_all([user_msg, bot_msg])
    sync_session.commit()
    return {"session": session, "user_msg": user_msg, "bot_msg": bot_msg}


async def test_feedback_upserts_per_user(client, login, seed, alice_conversation):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    mid = alice_conversation["bot_msg"].id

    r = await client.post(f"/chat/messages/{mid}/feedback", headers=alice,
                          json={"rating": "down", "reason": "citation wrong"})
    assert r.status_code == 204

    # Repeat feedback updates in place (no duplicate rows) …
    r = await client.post(f"/chat/messages/{mid}/feedback", headers=alice,
                          json={"rating": "up"})
    assert r.status_code == 204

    # … and the session detail reflects the caller's current rating.
    detail = (await client.get(f"/chat/sessions/{alice_conversation['session'].id}",
                               headers=alice)).json()
    ratings = {m["content"]: m["feedback"] for m in detail["messages"]}
    assert ratings["Antwort [1]."] == "up"
    assert ratings["Frage?"] is None


async def test_feedback_ownership_enforced(client, login, seed, alice_conversation):
    bob = await login(seed["bob"]["email"], seed["bob"]["password"])
    mid = alice_conversation["bot_msg"].id
    r = await client.post(f"/chat/messages/{mid}/feedback", headers=bob,
                          json={"rating": "up"})
    assert r.status_code == 404  # existence never leaks

    r = await client.post(f"/chat/messages/{uuid.uuid4()}/feedback", headers=bob,
                          json={"rating": "up"})
    assert r.status_code == 404


async def test_feedback_only_on_assistant_messages(client, login, seed, alice_conversation):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    mid = alice_conversation["user_msg"].id
    r = await client.post(f"/chat/messages/{mid}/feedback", headers=alice,
                          json={"rating": "up"})
    assert r.status_code == 400


async def test_feedback_requires_auth(client, alice_conversation):
    mid = alice_conversation["bot_msg"].id
    r = await client.post(f"/chat/messages/{mid}/feedback", json={"rating": "up"})
    assert r.status_code == 401


async def test_invalid_rating_rejected(client, login, seed, alice_conversation):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    mid = alice_conversation["bot_msg"].id
    r = await client.post(f"/chat/messages/{mid}/feedback", headers=alice,
                          json={"rating": "meh"})
    assert r.status_code == 422
