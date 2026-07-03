"""Phase 2 admin UI backend: GET /documents/{id}/ingest-status exposes the
latest ingest_jobs row (stage + failure reason), ACL-scoped."""

from __future__ import annotations

import uuid


async def _upload(client, headers, coll_id) -> str:
    r = await client.post(
        "/documents/upload", headers=headers,
        data={"collection_id": str(coll_id)},
        files={"file": ("notes.txt", b"Ingestion status endpoint test.")},
    )
    assert r.status_code == 201, r.text
    return r.json()["document"]["id"]


async def test_ingest_status_returns_queued_job(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    doc_id = await _upload(client, headers, seed["coll_a"])

    r = await client.get(f"/documents/{doc_id}/ingest-status", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["attempt"] == 0
    assert body["error"] is None


async def test_ingest_status_hidden_across_acl(client, seed, login):
    alice = await login(seed["alice"]["email"], seed["alice"]["password"])
    doc_id = await _upload(client, alice, seed["coll_a"])

    bob = await login(seed["bob"]["email"], seed["bob"]["password"])
    r = await client.get(f"/documents/{doc_id}/ingest-status", headers=bob)
    assert r.status_code == 404  # not visible to a different department


async def test_ingest_status_404_for_unknown_document(client, seed, login):
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])
    r = await client.get(f"/documents/{uuid.uuid4()}/ingest-status", headers=headers)
    assert r.status_code == 404
