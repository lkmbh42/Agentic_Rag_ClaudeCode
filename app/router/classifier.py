"""Query intent router (Phase 3).

Classifies a user question into one of four retrieval intents that select the
query-time path: `text` (hybrid text retrieval), `visual` (ColQwen2 page
retrieval fused with text), `metadata` (Postgres document lookup), `multi_doc`
(planner-led multi-step retrieval).

The LLM (classification model, Qwen2.5-3B role) does the classification with a
few-shot DE+EN prompt (app/graph/prompts.py: INTENT_ROUTER_SYSTEM, JSON-only).
Everything around the model is deterministic: the label is validated against
the closed intent set, and on ANY failure — unreachable backend, malformed
JSON, unknown label, empty query — the decision falls back to `text`, the safe
default that runs the proven hybrid text path (spec: deterministic fallback).

Latency is measured per call because the Phase 3 DoD gates p95 added router
latency at 400 ms (prod vLLM; the CPU dev model is exempt like all Phase 1+
latency targets).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.llm.client import LLMClient, get_class_llm

logger = logging.getLogger("rag.router")

INTENTS = frozenset({"text", "visual", "metadata", "multi_doc"})
FALLBACK_INTENT = "text"


@dataclass
class RouterDecision:
    intent: str
    source: str  # "llm" (validated model output) | "fallback" (deterministic)
    latency_ms: float


class IntentRouter:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or get_class_llm()

    def classify(self, query: str) -> RouterDecision:
        if not (query or "").strip():
            return RouterDecision(FALLBACK_INTENT, "fallback", 0.0)
        t0 = time.perf_counter()
        try:
            raw = self.llm.route_intent(query)
        except Exception as exc:  # noqa: BLE001 - router must never break the graph
            logger.warning("intent classification failed: %s", exc)
            raw = None
        latency_ms = (time.perf_counter() - t0) * 1000
        if raw in INTENTS:
            return RouterDecision(str(raw), "llm", latency_ms)
        return RouterDecision(FALLBACK_INTENT, "fallback", latency_ms)
