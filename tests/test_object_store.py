"""Phase 2 object store: bucket layout, round-trip, idempotent cleanup, URI
hygiene. Runs against the real dev MinIO service (in-network)."""

from __future__ import annotations

import uuid

import pytest

from app.ingestion import object_store as objstore
from app.ingestion.object_store import ObjectStore, parse_uri, to_uri

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


@pytest.fixture(scope="module")
def store() -> ObjectStore:
    s = ObjectStore()
    s.ensure_buckets()
    s.ensure_buckets()  # idempotent — second call must be a no-op
    return s


def test_uri_roundtrip():
    assert parse_uri(to_uri("figures", "abc/f1.png")) == ("figures", "abc/f1.png")
    for bad in ("http://x/y", "s3://", "s3://bucketonly", "figures/abc.png"):
        with pytest.raises(ValueError):
            parse_uri(bad)


def test_figure_and_page_roundtrip(store: ObjectStore):
    doc_id = uuid.uuid4()

    fig_uri = store.put_figure(doc_id, "fig-001", PNG_1PX)
    page_uri = store.put_page(doc_id, 3, PNG_1PX)

    # Spec bucket layout: figures/{doc_id}/{figure_id}.png, pages/{doc_id}/{page_no}.png
    assert fig_uri == f"s3://figures/{doc_id}/fig-001.png"
    assert page_uri == f"s3://pages/{doc_id}/3.png"
    assert store.get(fig_uri) == PNG_1PX
    assert store.get(page_uri) == PNG_1PX

    # Overwrite (re-ingest) must not error and must not duplicate.
    assert store.put_page(doc_id, 3, PNG_1PX) == page_uri

    # Spec: server-side encryption ON — every object must carry the SSE header
    # (MINIO_KMS_AUTO_ENCRYPTION=on + built-in KMS key).
    st = store._client.stat_object(*parse_uri(page_uri))
    assert st.metadata.get("X-Amz-Server-Side-Encryption") == "aws:kms"

    removed = store.delete_document(doc_id)
    assert removed == 2
    # Cleanup is idempotent: nothing left to remove.
    assert store.delete_document(doc_id) == 0
