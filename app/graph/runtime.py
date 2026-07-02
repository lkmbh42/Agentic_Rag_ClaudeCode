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

    return build_graph(get_llm(), checkpointer=build_checkpointer())
