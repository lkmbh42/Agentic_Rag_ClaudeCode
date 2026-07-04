"""Process-wide compiled graph singleton (real LLM + Postgres checkpointer).

Built lazily on first /chat call so importing the API never opens a DB pool or
requires the LLM at startup.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache
def get_graph():
    from app.graph.builder import build_graph
    from app.graph.checkpointer import build_checkpointer
    from app.llm.client import get_llm
    from app.router import IntentRouter

    # IntentRouter() binds to the classification model (llm_class_model,
    # Qwen2.5-3B role) — routing must not ride on the big generator in prod.
    return build_graph(get_llm(), checkpointer=build_checkpointer(),
                       intent_router=IntentRouter())
