"""RRF fusion of text-chunk and page-image rankings (Phase 3).

Per the spec, each modality keeps its own quality mechanism — text candidates
go through the (bge-)reranker inside the text retriever, visual pages are
ranked by MAX_SIM and capped at `visual_top_k_pages` — and RRF merges the two
already-ranked lists into ONE ordering that the context assembler consumes as
its packing priority. Standard reciprocal-rank fusion: each item contributes
1/(k + rank); `k` (`fusion_rrf_k`, default 60) damps the head of each list.

Ties (e.g. rank-1 text vs rank-1 page) resolve text-first: text context is the
proven answer path and page images are the (budget-capped) enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings

_settings = get_settings()

KIND_CHUNK = "chunk"
KIND_PAGE = "page"


@dataclass
class FusedCandidate:
    kind: str  # KIND_CHUNK | KIND_PAGE
    item: dict  # the chunk dict or page-hit dict (graph-state shape)
    rrf_score: float


def rrf_merge(chunks: list[dict], pages: list[dict],
              k: int | None = None) -> list[FusedCandidate]:
    """Merge two ranked lists (best first) into one RRF-ordered list."""
    k = k or _settings.fusion_rrf_k
    fused = [FusedCandidate(KIND_CHUNK, c, 1.0 / (k + rank))
             for rank, c in enumerate(chunks, start=1)]
    fused += [FusedCandidate(KIND_PAGE, p, 1.0 / (k + rank))
              for rank, p in enumerate(pages, start=1)]
    # Stable sort: equal scores keep insertion order, i.e. text before pages.
    fused.sort(key=lambda f: f.rrf_score, reverse=True)
    return fused
