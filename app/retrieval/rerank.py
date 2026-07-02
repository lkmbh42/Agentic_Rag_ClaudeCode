"""Rerankers. Dev uses a lexical (token-overlap) reranker; prod calls the
bge-reranker-v2-m3 cross-encoder in the embeddings service."""

from __future__ import annotations

import re
from typing import Protocol

_TOKEN = re.compile(r"\w+")


class Reranker(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[float]:
        """Return a relevance score per doc (higher = better), aligned to `docs`."""
        ...


class NoopReranker:
    """Preserves the upstream (RRF) ordering."""

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        return [float(len(docs) - i) for i in range(len(docs))]


class LexicalReranker:
    """Token-overlap (Jaccard-ish) scoring — a real signal without a model."""

    def rerank(self, query: str, docs: list[str]) -> list[float]:
        q = set(_TOKEN.findall(query.lower()))
        if not q:
            return [0.0] * len(docs)
        scores = []
        for doc in docs:
            d = set(_TOKEN.findall(doc.lower()))
            overlap = len(q & d)
            scores.append(overlap / (len(q) + 1e-9))
        return scores
