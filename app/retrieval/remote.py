"""Clients for the BGE-M3 embeddings service (prod backend).

These call the `embeddings` container's /embed and /rerank endpoints. Used when
EMBEDDINGS_BACKEND=service / RERANKER_BACKEND=service. Sync (httpx.Client) so the
same code path serves both the worker (indexing) and the retriever.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_settings = get_settings()


class ServiceEmbedder:
    """Calls BGE-M3 in the embeddings service. dim must match the served model."""

    def __init__(self, base_url: str | None = None, dim: int | None = None) -> None:
        self.base_url = (base_url or _settings.embeddings_base_url).rstrip("/")
        self.dim = dim or _settings.embedding_dim
        self._client = httpx.Client(timeout=60)

    def _embed(self, text: str) -> dict:
        resp = self._client.post(f"{self.base_url}/embed", json={"texts": [text]})
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    def embed_dense(self, text: str) -> list[float]:
        return self._embed(text)["dense"]

    def embed_sparse(self, text: str) -> tuple[list[int], list[float]]:
        sp = self._embed(text)["sparse"]
        return sp["indices"], sp["values"]


# Cross-encoder cost is ~linear in each doc's token count. On CPU (dev) a full
# 1.8k-char table chunk dominates the whole request (~50s for 10 docs). Only the
# head of a chunk is needed to JUDGE relevance — the full content still goes to
# the generator — so we truncate the reranker's view. 400 chars keeps a table's
# leading rows (the numbers that make it match) while cutting rerank time ~3x.
_RERANK_DOC_CHARS = 300


class ServiceReranker:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or _settings.embeddings_base_url).rstrip("/")
        self._client = httpx.Client(timeout=120)

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        clipped = [d[:_RERANK_DOC_CHARS] for d in docs]
        resp = self._client.post(
            f"{self.base_url}/rerank", json={"query": query, "documents": clipped}
        )
        resp.raise_for_status()
        return resp.json()["scores"]
