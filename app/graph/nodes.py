"""Graph nodes. Each returns a partial state update and bumps the iteration
counter (the master circuit breaker). LLM / retriever / cache are injected so the
graph is fully testable with fakes."""

from __future__ import annotations

import json
import logging
import time
import uuid

import redis as sync_redis

from app.config import get_settings
from app.graph.citations import extract_citations
from app.llm.client import LLMClient
from app.graph.state import COMPLEX_ROUTES, INSUFFICIENT_ANSWER, GraphState
from app.retrieval.retriever import Retriever
from app.retrieval.semantic_cache import SemanticCache

logger = logging.getLogger("rag.graph.nodes")
_settings = get_settings()


def _bump(state: GraphState) -> int:
    return state.get("iterations", 0) + 1


def _uuids(ids: list[str]) -> set[uuid.UUID]:
    out = set()
    for i in ids:
        try:
            out.add(uuid.UUID(i))
        except (ValueError, TypeError):
            continue
    return out


class Nodes:
    def __init__(
        self,
        llm: LLMClient,
        retriever: Retriever | None = None,
        cache: SemanticCache | None = None,
        redis_client=None,
    ) -> None:
        self.llm = llm
        self.retriever = retriever or Retriever()
        self.cache = cache or SemanticCache()
        self.redis = redis_client or sync_redis.from_url(_settings.redis_url, decode_responses=True)

    # ------------------------------------------------------------------ nodes
    def input_guard(self, state: GraphState) -> dict:
        query = (state.get("query") or "").strip()
        update = {"iterations": _bump(state), "retrieval_retries": state.get("retrieval_retries", 0),
                  "generation_retries": state.get("generation_retries", 0)}
        if not query:
            update.update(insufficient=True, answer="Empty query.",
                          messages=[{"role": "assistant", "content": "Empty query."}])
        return update

    def semantic_cache(self, state: GraphState) -> dict:
        allowed = _uuids(state.get("allowed_collection_ids", []))
        hit = self.cache.lookup(allowed, state["query"]) if allowed else None
        if hit is not None:
            return {
                "iterations": _bump(state), "cache_hit": True, "answer": hit.answer,
                "citations": [{"document_id": d} for d in hit.document_ids],
                "messages": [{"role": "assistant", "content": hit.answer}],
            }
        return {"iterations": _bump(state), "cache_hit": False}

    def router(self, state: GraphState) -> dict:
        return {"iterations": _bump(state), "route": self.llm.route(state["query"])}

    def planner(self, state: GraphState) -> dict:
        return {"iterations": _bump(state), "plan": self.llm.plan(state["query"])}

    def retriever_node(self, state: GraphState) -> dict:
        allowed = _uuids(state.get("allowed_collection_ids", []))
        query = state.get("rewritten_query") or state["query"]
        # Contextualize a follow-up with the previous user turn so a vague query
        # ("tell me more") still retrieves the right topic.
        if not state.get("rewritten_query"):
            prior = [m["content"] for m in state.get("messages", [])
                     if m.get("role") == "user"][:-1]
            if prior:
                query = f"{prior[-1]} {query}"
        t0 = time.perf_counter()
        chunks = self.retriever.search(allowed, query) if allowed else []
        elapsed = (time.perf_counter() - t0) * 1000
        return {"iterations": _bump(state),
                "retrieval_latency_ms": elapsed,
                "chunks": [
            {"chunk_id": str(c.chunk_id), "document_id": str(c.document_id),
             "collection_id": str(c.collection_id), "chunk_type": c.chunk_type,
             "page_number": c.page_number, "section_title": c.section_title,
             "content": c.content, "score": c.score}
            for c in chunks
        ]}

    def retrieval_grader(self, state: GraphState) -> dict:
        chunks = state.get("chunks", [])
        ok = bool(chunks) and self.llm.grade_relevance(
            state["query"], [c["content"] for c in chunks])
        return {"iterations": _bump(state), "relevance_ok": ok}

    def rewrite(self, state: GraphState) -> dict:
        return {
            "iterations": _bump(state),
            "retrieval_retries": state.get("retrieval_retries", 0) + 1,
            "rewritten_query": self.llm.rewrite_query(state["query"]),
        }

    def generator(self, state: GraphState) -> dict:
        chunks = state.get("chunks", [])
        # In a custom-stream run, tokens flow to the SSE writer; otherwise no-op.
        writer = None
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
        except Exception:  # noqa: BLE001 - not in a streaming context
            writer = None

        # Prior turns (everything before the current user message) let the model
        # resolve follow-ups like "tell me more" / "erklär mir mehr".
        history = [m for m in state.get("messages", [])
                   if m.get("role") in ("user", "assistant")][:-1]
        t0 = time.perf_counter()
        answer = self.llm.generate(
            state["query"], [c["content"] for c in chunks],
            on_token=writer if callable(writer) else None,
            history=history,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        # Citations come ONLY from [n] markers the model actually wrote.
        citations = extract_citations(answer, chunks)
        return {"iterations": _bump(state), "answer": answer,
                "citations": citations, "generation_latency_ms": elapsed}

    def hallucination_grader(self, state: GraphState) -> dict:
        answer = (state.get("answer") or "").strip()
        if not _settings.hallucination_check_enabled:
            # Trust the generator (weak dev grader gives false negatives), but
            # still reject empty / self-abstained answers.
            grounded = bool(answer) and answer != INSUFFICIENT_ANSWER
        else:
            grounded = self.llm.grade_grounded(
                answer, [c["content"] for c in state.get("chunks", [])])
        return {"iterations": _bump(state), "grounded": grounded}

    def retry_generation(self, state: GraphState) -> dict:
        return {"iterations": _bump(state),
                "generation_retries": state.get("generation_retries", 0) + 1}

    def insufficient(self, state: GraphState) -> dict:
        return {"iterations": _bump(state), "insufficient": True,
                "answer": INSUFFICIENT_ANSWER, "citations": [],
                "messages": [{"role": "assistant", "content": INSUFFICIENT_ANSWER}]}

    def unsupported(self, state: GraphState) -> dict:
        msg = "That request type isn't supported."
        return {"iterations": _bump(state), "insufficient": True, "answer": msg,
                "messages": [{"role": "assistant", "content": msg}]}

    def finalize_answer(self, state: GraphState) -> dict:
        # Grounded answer accepted; record assistant message.
        return {"iterations": _bump(state),
                "messages": [{"role": "assistant", "content": state.get("answer", "")}]}

    def cache_writer(self, state: GraphState) -> dict:
        chunks = state.get("chunks", [])
        if state.get("answer") and chunks and not state.get("insufficient"):
            try:
                self.cache.store(
                    state["query"], state["answer"],
                    {uuid.UUID(c["collection_id"]) for c in chunks},
                    {uuid.UUID(c["document_id"]) for c in chunks},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("cache write failed: %s", exc)
        return {"iterations": _bump(state)}

    def eval_queue(self, state: GraphState) -> dict:
        if not _settings.eval_enabled:
            return {"iterations": _bump(state)}
        chunks = state.get("chunks", [])
        try:
            self.redis.rpush(_settings.eval_queue, json.dumps({
                "request_id": state.get("request_id"),
                "query": state.get("query"), "answer": state.get("answer", ""),
                "route": state.get("route"), "cache_hit": state.get("cache_hit", False),
                "contexts": [c["content"] for c in chunks],
                "retrieved_document_ids": sorted({c["document_id"] for c in chunks}),
                "citations": state.get("citations", []),
                "insufficient": state.get("insufficient", False),
            }))
        except Exception as exc:  # noqa: BLE001 - eval must never block the answer
            logger.warning("eval enqueue failed: %s", exc)
        return {"iterations": _bump(state)}
