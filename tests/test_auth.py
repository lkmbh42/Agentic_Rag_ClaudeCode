"""Auth DoD: login issues a JWT; the JWT validates; revocation works."""

from __future__ import annotations


async def test_login_success_and_me(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == seed["alice"]["email"]
    assert body["role"] == "user"


async def test_login_wrong_password_401(client, seed):
    resp = await client.post(
        "/auth/login",
        json={"email": seed["alice"]["email"], "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user_401(client, seed):
    resp = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert resp.status_code == 401


async def test_me_requires_token(client, seed):
    assert (await client.get("/auth/me")).status_code == 401


async def test_refresh_token_cannot_authenticate(client, seed):
    resp = await client.post(
        "/auth/login",
        json={"email": seed["bob"]["email"], "password": seed["bob"]["password"]},
    )
    refresh = resp.json()["refresh_token"]
    # A refresh token must not be accepted as an access token.
    bad = await client.get("/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert bad.status_code == 401


async def test_refresh_rotates_and_old_token_revoked(client, seed):
    resp = await client.post(
        "/auth/login",
        json={"email": seed["bob"]["email"], "password": seed["bob"]["password"]},
    )
    old_refresh = resp.json()["refresh_token"]
    r1 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200
    # Reusing the rotated refresh token must fail.
    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


async def test_logout_revokes_access_token(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    assert (await client.get("/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    # Same token must now be rejected.
    assert (await client.get("/auth/me", headers=headers)).status_code == 401
