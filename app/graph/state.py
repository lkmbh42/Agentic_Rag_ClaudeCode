"""Graph state.

`messages` accumulates across turns (reducer = list concat); the Postgres
checkpointer persists the whole state per thread_id (= chat session id), so a
multi-turn conversation resumes after a server restart.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

# LEGACY router categories (pre-Phase-3). Superseded by the 4-intent router
# (app/router/, CLAUDE.md Phase 3): text | visual | metadata | multi_doc.
# Kept only because LLMClient.route() still exists for rollback; the graph no
# longer consumes these.
ROUTES = {
    "simple_rag", "complex_multi_step", "summarization", "comparison",
    "table_question", "chart_question", "diagram_question", "image_question",
    "unsupported",
}
COMPLEX_ROUTES = {"complex_multi_step", "comparison", "summarization"}

INSUFFICIENT_ANSWER = (
    "I don't have enough supporting evidence in the documents you can access to "
    "answer that confidently."
)


class GraphState(TypedDict, total=False):
    messages: Annotated[list, operator.add]

    # request context (set by the caller)
    query: str
    allowed_collection_ids: list[str]
    request_id: str

    # observability (set by nodes)
    retrieval_latency_ms: float
    generation_latency_ms: float
    router_latency_ms: float

    # working state
    rewritten_query: str
    route: str  # exposed to API/audit; carries the intent since Phase 3
    intent: str  # text | visual | metadata | multi_doc (app/router/)
    intent_source: str  # "llm" | "fallback"
    plan: list[str]
    chunks: list[dict]
    page_hits: list[dict]  # visual intent: ColQwen2 page hits (Phase 3)
    answer: str
    citations: list[dict]

    # context assembly (Phase 3)
    context_tokens: int
    context_images: int

    # flags
    cache_hit: bool
    relevance_ok: bool
    grounded: bool
    insufficient: bool

    # circuit-breaker counters
    retrieval_retries: int
    generation_retries: int
    iterations: int
