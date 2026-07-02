"""Backend selection for embedder + reranker.

One factory used by BOTH the worker (index-time) and the retriever (query-time),
so index and query embeddings always come from the same backend.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.ingestion.embedder import Embedder, HashingEmbedder
from app.retrieval.rerank import LexicalReranker, NoopReranker, Reranker

_settings = get_settings()


@lru_cache
def get_embedder() -> Embedder:
    backend = _settings.embeddings_backend.lower()
    if backend == "service":
        from app.retrieval.remote import ServiceEmbedder

        return ServiceEmbedder(dim=_settings.embedding_dim)
    if backend == "hashing":
        return HashingEmbedder(dim=_settings.embedding_dim)
    raise ValueError(f"Unknown EMBEDDINGS_BACKEND: {backend!r}")


@lru_cache
def get_reranker() -> Reranker:
    backend = _settings.reranker_backend.lower()
    if backend == "service":
        from app.retrieval.remote import ServiceReranker

        return ServiceReranker()
    if backend == "lexical":
        return LexicalReranker()
    if backend == "none":
        return NoopReranker()
    raise ValueError(f"Unknown RERANKER_BACKEND: {backend!r}")
