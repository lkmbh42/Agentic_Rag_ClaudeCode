"""Embedding interface + a deterministic local implementation.

The `Embedder` protocol is the seam Phase 4 plugs BGE-M3 (+ reranker) into. The
`HashingEmbedder` here is a real, dependency-free embedder (feature hashing) used
so the ingestion pipeline is end-to-end into Qdrant from Phase 3 — it produces
both a fixed-size dense vector and a sparse vector, matching the Qdrant schema
BGE-M3 will use. It is NOT semantically strong; Phase 4 replaces it transparently.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"\w+")
_SPARSE_SPACE = 2**20


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _h(token: str, mod: int) -> int:
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:8], "big") % mod


class Embedder(Protocol):
    dim: int

    def embed_dense(self, text: str) -> list[float]: ...
    def embed_sparse(self, text: str) -> tuple[list[int], list[float]]: ...


class HashingEmbedder:
    """Feature-hashing embedder. Deterministic, local, no model download."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed_dense(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokens(text):
            idx = _h(tok, self.dim)
            # signed contribution to spread mass
            sign = 1.0 if _h(tok + "#", 2) == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        else:
            # Non-zero placeholder so cosine distance is defined for empty text.
            vec[0] = 1.0
        return vec

    def embed_sparse(self, text: str) -> tuple[list[int], list[float]]:
        counts: dict[int, float] = {}
        for tok in _tokens(text):
            counts[_h(tok, _SPARSE_SPACE)] = counts.get(_h(tok, _SPARSE_SPACE), 0.0) + 1.0
        if not counts:
            return [], []
        indices = sorted(counts)
        values = [counts[i] for i in indices]
        return indices, values
