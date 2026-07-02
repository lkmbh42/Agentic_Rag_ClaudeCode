"""Session-ownership DoD: a non-admin must never fetch another user's session."""

from __future__ import annotations


async def _create_session(client, headers, title="s") -> str:
    resp = await client.post("/chat/sessions", headers=headers, json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_owner_can_fetch_session(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    sid = await _create_session(client, headers)
    resp = await client.get(f"/chat/sessions/{sid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == sid


async def test_non_owner_cannot_fetch_session(client, seed, login):
    alice_h = await login(seed["alice"]["email"], seed["alice"]["password"])
    sid = await _create_session(client, alice_h)

    bob_h = await login(seed["bob"]["email"], seed["bob"]["password"])
    resp = await client.get(f"/chat/sessions/{sid}", headers=bob_h)
    assert resp.status_code == 404  # not 403 — don't leak existence


async def test_session_list_is_scoped_to_user(client, seed, login):
    alice_h = await login(seed["alice"]["email"], seed["alice"]["password"])
    await _create_session(client, alice_h, "a1")
    await _create_session(client, alice_h, "a2")

    bob_h = await login(seed["bob"]["email"], seed["bob"]["password"])
    await _create_session(client, bob_h, "b1")

    assert len((await client.get("/chat/sessions", headers=alice_h)).json()) == 2
    assert len((await client.get("/chat/sessions", headers=bob_h)).json()) == 1


async def test_sessions_require_auth(client, seed):
    assert (await client.get("/chat/sessions")).status_code == 401
