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


async def test_logout_revokes_access_and_refresh(client, seed):
    """Logout must end the whole session: the refresh token can't outlive it
    (previously only the access token was revoked, leaving refresh valid 7 days)."""
    resp = await client.post(
        "/auth/login",
        json={"email": seed["bob"]["email"], "password": seed["bob"]["password"]},
    )
    access = resp.json()["access_token"]
    refresh = resp.json()["refresh_token"]

    out = await client.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert out.status_code == 204

    # The access token is denylisted...
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})).status_code == 401
    # ...and the refresh token can no longer mint a new pair.
    assert (await client.post("/auth/refresh", json={"refresh_token": refresh})).status_code == 401


async def test_login_sets_httponly_refresh_cookie(client, seed):
    resp = await client.post(
        "/auth/login",
        json={"email": seed["bob"]["email"], "password": seed["bob"]["password"]},
    )
    cookie = resp.headers.get("set-cookie", "")
    assert "recherche_refresh=" in cookie and "HttpOnly" in cookie
    # A browser with only the cookie (no body) can refresh.
    r = await client.post("/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]


async def test_refresh_rejected_after_session_epoch_bump(client, seed):
    """Regression: revoke-sessions must also kill refresh tokens, not just
    access tokens — otherwise a refresh mints a fresh valid pair."""
    from app.core.redis import bump_session_epoch

    resp = await client.post(
        "/auth/login",
        json={"email": seed["bob"]["email"], "password": seed["bob"]["password"]},
    )
    refresh = resp.json()["refresh_token"]
    await bump_session_epoch(seed["bob"]["id"])
    r = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_refresh_with_malformed_sub_401(client, seed):
    from app.core import security

    token = security.jwt.encode(
        {"sub": "not-a-uuid", "type": security.REFRESH, "jti": "x",
         "iat": 0, "exp": 4102444800},
        security._settings.jwt_secret, algorithm=security._settings.jwt_algorithm,
    )
    r = await client.post("/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 401


async def test_logout_revokes_access_token(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    assert (await client.get("/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/auth/logout", headers=headers)).status_code == 204
    # Same token must now be rejected.
    assert (await client.get("/auth/me", headers=headers)).status_code == 401
