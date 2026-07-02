"""RBAC DoD: a user cannot read another department's collection.

Also covers admin-wide access, explicit cross-department grants, and admin-route
gating.
"""

from __future__ import annotations


async def test_user_lists_only_own_department(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    resp = await client.get("/collections", headers=headers)
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()}
    assert ids == {str(seed["coll_a"])}


async def test_user_can_read_own_collection(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    resp = await client.get(f"/collections/{seed['coll_a']}", headers=headers)
    assert resp.status_code == 200


async def test_cross_department_collection_denied(client, seed, login):
    # The core DoD: alice (dept A) must NOT read collB (dept B).
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    resp = await client.get(f"/collections/{seed['coll_b']}", headers=headers)
    assert resp.status_code == 404  # 404 (not 403) to avoid leaking existence


async def test_admin_sees_all_collections(client, seed, login):
    headers = await login(seed["admin"]["email"], seed["admin"]["password"])
    resp = await client.get("/collections", headers=headers)
    ids = {c["id"] for c in resp.json()}
    assert ids == {str(seed["coll_a"]), str(seed["coll_b"])}
    assert (await client.get(f"/collections/{seed['coll_b']}", headers=headers)).status_code == 200


async def test_explicit_grant_enables_cross_department_access(client, seed, login):
    admin_h = await login(seed["admin"]["email"], seed["admin"]["password"])
    # Grant alice (as user) read access to collB.
    grant = await client.post(
        "/admin/permissions",
        headers=admin_h,
        json={
            "principal_type": "user",
            "principal_id": str(seed["alice"]["id"]),
            "resource_type": "collection",
            "resource_id": str(seed["coll_b"]),
            "access_level": "read",
        },
    )
    assert grant.status_code == 201

    alice_h = await login(seed["alice"]["email"], seed["alice"]["password"])
    resp = await client.get(f"/collections/{seed['coll_b']}", headers=alice_h)
    assert resp.status_code == 200


async def test_non_admin_blocked_from_admin_routes(client, seed, login):
    alice_h = await login(seed["alice"]["email"], seed["alice"]["password"])
    resp = await client.post(
        "/admin/departments", headers=alice_h, json={"name": "Sneaky"}
    )
    assert resp.status_code == 403
