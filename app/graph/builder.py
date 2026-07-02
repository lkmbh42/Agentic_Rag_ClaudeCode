"""Assemble the agent graph with circuit-breaker routing.

Termination guarantee:
  - every node increments `iterations`;
  - retrieval retries are bounded by MAX_RETRIEVAL_RETRIES (rewrite loop);
  - generation retries are bounded by MAX_GENERATION_RETRIES;
  - a global cap MAX_GRAPH_ITERATIONS is the hard backstop: once exceeded, every
    conditional routes to the terminal answer -> eval_queue -> END.
Together these make every path provably finite.

Note: node ids must not collide with GraphState keys, so the terminal node is
`insufficient_answer` (the state flag it sets is `insufficient`).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.llm.client import LLMClient
from app.graph.nodes import Nodes
from app.graph.state import COMPLEX_ROUTES, GraphState

_settings = get_settings()
_TERMINAL = "insufficient_answer"


def _over_budget(state: GraphState) -> bool:
    return state.get("iterations", 0) >= _settings.max_graph_iterations


def _after_input(state: GraphState) -> str:
    return "eval_queue" if state.get("insufficient") else "semantic_cache"


def _after_cache(state: GraphState) -> str:
    return "eval_queue" if state.get("cache_hit") else "router"


def _after_router(state: GraphState) -> str:
    if _over_budget(state):
        return _TERMINAL
    # Note: we deliberately do NOT dead-end on an "unsupported" classification —
    # small models over-use it (esp. on follow-ups / non-English). Always try to
    # answer from the documents; weak/irrelevant retrieval yields a safe reply.
    if state.get("route") in COMPLEX_ROUTES:
        return "planner"
    return "retriever"


def _after_grade(state: GraphState) -> str:
    if _over_budget(state):
        return _TERMINAL
    if state.get("relevance_ok"):
        return "generator"
    if state.get("retrieval_retries", 0) < _settings.max_retrieval_retries:
        return "rewrite"
    return "generator" if state.get("chunks") else _TERMINAL


def _after_halluc(state: GraphState) -> str:
    if _over_budget(state):
        return _TERMINAL
    if state.get("grounded"):
        return "finalize_answer"
    if state.get("generation_retries", 0) < _settings.max_generation_retries:
        return "retry_generation"
    return _TERMINAL


def build_graph(llm: LLMClient, *, checkpointer=None, retriever=None, cache=None,
                redis_client=None):
    n = Nodes(llm, retriever=retriever, cache=cache, redis_client=redis_client)
    g = StateGraph(GraphState)

    g.add_node("input_guard", n.input_guard)
    g.add_node("semantic_cache", n.semantic_cache)
    g.add_node("router", n.router)
    g.add_node("planner", n.planner)
    g.add_node("retriever", n.retriever_node)
    g.add_node("retrieval_grader", n.retrieval_grader)
    g.add_node("rewrite", n.rewrite)
    g.add_node("generator", n.generator)
    g.add_node("hallucination_grader", n.hallucination_grader)
    g.add_node("retry_generation", n.retry_generation)
    g.add_node("finalize_answer", n.finalize_answer)
    g.add_node("cache_writer", n.cache_writer)
    g.add_node("unsupported", n.unsupported)
    g.add_node(_TERMINAL, n.insufficient)
    g.add_node("eval_queue", n.eval_queue)

    g.add_edge(START, "input_guard")
    g.add_conditional_edges("input_guard", _after_input, ["semantic_cache", "eval_queue"])
    g.add_conditional_edges("semantic_cache", _after_cache, ["router", "eval_queue"])
    g.add_conditional_edges("router", _after_router,
                            ["planner", "retriever", "unsupported", _TERMINAL])
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "retrieval_grader")
    g.add_conditional_edges("retrieval_grader", _after_grade,
                            ["generator", "rewrite", _TERMINAL])
    g.add_edge("rewrite", "retriever")
    g.add_edge("generator", "hallucination_grader")
    g.add_conditional_edges("hallucination_grader", _after_halluc,
                            ["finalize_answer", "retry_generation", _TERMINAL])
    g.add_edge("retry_generation", "generator")
    g.add_edge("finalize_answer", "cache_writer")
    g.add_edge("cache_writer", "eval_queue")
    g.add_edge("unsupported", "eval_queue")
    g.add_edge(_TERMINAL, "eval_queue")
    g.add_edge("eval_queue", END)

    return g.compile(checkpointer=checkpointer)
