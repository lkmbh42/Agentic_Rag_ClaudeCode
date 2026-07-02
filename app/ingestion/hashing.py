"""Content hashing for dedup and per-chunk change detection."""

from __future__ import annotations

import hashlib


def content_hash(data: bytes) -> str:
    """SHA-256 of raw file bytes — the document-level dedup key."""
    return hashlib.sha256(data).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
