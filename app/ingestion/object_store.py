"""MinIO object store for ingestion artifacts (Phase 2).

Bucket layout (spec):
    figures/{doc_id}/{figure_id}.png   — cropped figure regions
    pages/{doc_id}/{page_no}.png       — full-page renders (≤1024 px longest edge)

Access rule (Rule 5 / ACL invariant): objects are NEVER exposed via presigned or
public URLs. The only read path is the gateway, which re-checks the requesting
user's ACL before proxying bytes (Phase 4). This module is the single writer
and internal reader.

URIs are stored in Qdrant payloads as `s3://{bucket}/{key}` — resolvable only
through this module, meaningless outside the internal network.
"""

from __future__ import annotations

import io
import logging
import uuid
from functools import lru_cache

from minio import Minio
from minio.deleteobjects import DeleteObject

from app.config import get_settings

logger = logging.getLogger("rag.ingestion.object_store")
_settings = get_settings()

_PNG = "image/png"


def figure_key(document_id: uuid.UUID | str, figure_id: str) -> str:
    return f"{document_id}/{figure_id}.png"


def page_key(document_id: uuid.UUID | str, page_no: int) -> str:
    return f"{document_id}/{page_no}.png"


def to_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def parse_uri(uri: str) -> tuple[str, str]:
    """`s3://bucket/key` → (bucket, key). Raises ValueError on anything else."""
    if not uri.startswith("s3://"):
        raise ValueError(f"not an internal object uri: {uri!r}")
    bucket, _, key = uri[len("s3://"):].partition("/")
    if not bucket or not key:
        raise ValueError(f"malformed object uri: {uri!r}")
    return bucket, key


class ObjectStore:
    """Thin typed wrapper over the MinIO client for the two ingestion buckets."""

    def __init__(self) -> None:
        self._client = Minio(
            _settings.minio_endpoint,
            access_key=_settings.minio_access_key,
            secret_key=_settings.minio_secret_key,
            secure=_settings.minio_secure,
        )

    def ensure_buckets(self) -> None:
        """Idempotent bucket creation (worker startup + first use)."""
        for bucket in (_settings.minio_bucket_figures, _settings.minio_bucket_pages):
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
                logger.info("created bucket %s", bucket)

    # ------------------------------------------------------------------ write
    def put_figure(self, document_id: uuid.UUID | str, figure_id: str,
                   png: bytes) -> str:
        return self._put(_settings.minio_bucket_figures,
                         figure_key(document_id, figure_id), png)

    def put_page(self, document_id: uuid.UUID | str, page_no: int,
                 png: bytes) -> str:
        return self._put(_settings.minio_bucket_pages,
                         page_key(document_id, page_no), png)

    def _put(self, bucket: str, key: str, png: bytes) -> str:
        self._client.put_object(bucket, key, io.BytesIO(png), length=len(png),
                                content_type=_PNG)
        return to_uri(bucket, key)

    # ------------------------------------------------------------------- read
    def get(self, uri: str) -> bytes:
        bucket, key = parse_uri(uri)
        resp = self._client.get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    # ----------------------------------------------------------------- delete
    def delete_document(self, document_id: uuid.UUID | str) -> int:
        """Remove every object for a document (delete / re-ingest cleanup).
        Idempotent: deleting a missing prefix is a no-op. Returns count removed."""
        removed = 0
        for bucket in (_settings.minio_bucket_figures, _settings.minio_bucket_pages):
            names = [o.object_name for o in
                     self._client.list_objects(bucket, prefix=f"{document_id}/",
                                               recursive=True)]
            if not names:
                continue
            errors = list(self._client.remove_objects(
                bucket, [DeleteObject(n) for n in names]))
            for err in errors:  # pragma: no cover - surfaced, not swallowed
                logger.error("delete failed %s/%s: %s", bucket, err.name, err)
            removed += len(names) - len(errors)
        return removed


@lru_cache
def get_object_store() -> ObjectStore:
    return ObjectStore()
