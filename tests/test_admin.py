"""Phase 9 admin DoD: non-admin rejected by /admin/*; suspend & revoke-sessions
terminate active sessions; reset-credential rotates; revoking a permission
invalidates the relevant cache entries."""

from __future__ import annotations

import uuid


async def _make_user(client, admin_h, email, password="user-pass-123", dept=None):
    body = {"email": email, "password": password, "role": "user"}
    if dept is not None:
        body["department_id"] = str(dept)
    r = await client.post("/admin/users", headers=admin_h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_non_admin_rejected_by_admin_routes(client, seed, login):
    h = await login(seed["alice"]["email"], seed["alice"]["password"])
    assert (await client.get("/admin/users", headers=h)).status_code == 403
    assert (await client.get("/admin/metrics", headers=h)).status_code == 403
    assert (await client.post("/admin/departments", headers=h, json={"name": "x"})).status_code == 403
    assert (await client.delete(f"/admin/permissions/{uuid.uuid4()}", headers=h)).status_code == 403


async def test_suspend_terminates_sessions(client, seed, login):
    admin_h = await login(seed["admin"]["email"], seed["admin"]["password"])
    uid = await _make_user(client, admin_h, "victim@example.com", dept=seed["dept_a"])

    user_h = await login("victim@example.com", "user-pass-123")
    assert (await client.get("/auth/me", headers=user_h)).status_code == 200

    r = await client.patch(f"/admin/users/{uid}", headers=admin_h, json={"is_active": False})
    assert r.status_code == 200
    # Existing token is now dead.
    assert (await client.get("/auth/me", headers=user_h)).status_code == 401


async def test_revoke_sessions_kills_token(client, seed, login):
    admin_h = await login(seed["admin"]["email"], seed["admin"]["password"])
    uid = await _make_user(client, admin_h, "revoke@example.com", dept=seed["dept_a"])
    user_h = await login("revoke@example.com", "user-pass-123")
    assert (await client.get("/auth/me", headers=user_h)).status_code == 200

    assert (await client.post(f"/admin/users/{uid}/revoke-sessions", headers=admin_h)).status_code == 204
    assert (await client.get("/auth/me", headers=user_h)).status_code == 401


async def test_reset_credential_rotates_and_invalidates(client, seed, login):
    admin_h = await login(seed["admin"]["email"], seed["admin"]["password"])
    uid = await _make_user(client, admin_h, "reset@example.com", dept=seed["dept_a"])
    old_h = await login("reset@example.com", "user-pass-123")

    r = await client.post(f"/admin/users/{uid}/reset-credential", headers=admin_h)
    assert r.status_code == 200
    temp = r.json()["temporary_password"]
    # Old session invalidated; new credential works.
    assert (await client.get("/auth/me", headers=old_h)).status_code == 401
    new_h = await login("reset@example.com", temp)
    assert (await client.get("/auth/me", headers=new_h)).status_code == 200


async def test_revoke_permission_invalidates_cache(client, seed, login):
    from app.retrieval.semantic_cache import SemanticCache

    admin_h = await login(seed["admin"]["email"], seed["admin"]["password"])
    # Grant alice cross-dept access to coll_b.
    grant = await client.post("/admin/permissions", headers=admin_h, json={
        "principal_type": "user", "principal_id": str(seed["alice"]["id"]),
        "resource_type": "collection", "resource_id": str(seed["coll_b"]),
        "access_level": "read",
    })
    perm_id = grant.json()["id"]

    # Seed a cache entry whose source scope includes coll_b.
    sc = SemanticCache()
    sc.ensure_collection()
    q = f"cache probe {uuid.uuid4()}"
    sc.store(q, "cached answer", {seed["coll_b"]}, {uuid.uuid4()})
    assert sc.lookup({seed["coll_b"]}, q) is not None

    # Revoking the permission must evict cache entries scoped to that collection.
    r = await client.delete(f"/admin/permissions/{perm_id}", headers=admin_h)
    assert r.status_code == 204
    assert sc.lookup({seed["coll_b"]}, q) is None
