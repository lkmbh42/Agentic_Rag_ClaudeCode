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
from app.graph.state import INSUFFICIENT_ANSWER, GraphState
from app.retrieval.retriever import Retriever
from app.retrieval.semantic_cache import SemanticCache
from app.retrieval.visual import VisualRetriever
from app.router import IntentRouter

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
        visual_retriever: VisualRetriever | None = None,
        intent_router: IntentRouter | None = None,
        session_factory=None,
    ) -> None:
        self.llm = llm
        self.retriever = retriever or Retriever()
        self.cache = cache or SemanticCache()
        self.redis = redis_client or sync_redis.from_url(_settings.redis_url, decode_responses=True)
        self.visual = visual_retriever or VisualRetriever()
        # Default: route with the SAME injected client (deterministic in tests).
        # The prod runtime injects IntentRouter() so routing stays on the small
        # classification model (Qwen2.5-3B role) — see app/graph/runtime.py.
        self.intent_router = intent_router or IntentRouter(llm=llm)
        # Sync DB sessions for the metadata path (the graph runs off-loop).
        if session_factory is None:
            from app.db.sync_session import SyncSessionLocal

            session_factory = SyncSessionLocal
        self.session_factory = session_factory

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
                # Full stored citations (verifiable sources); fall back to bare
                # document ids for legacy entries written before citations were cached.
                "citations": hit.citations or [{"document_id": d} for d in hit.document_ids],
                "messages": [{"role": "assistant", "content": hit.answer}],
            }
        return {"iterations": _bump(state), "cache_hit": False}

    def router(self, state: GraphState) -> dict:
        """Phase 3 intent router (text|visual|metadata|multi_doc). `route` is
        kept in lock-step with `intent` for the API/audit surface."""
        decision = self.intent_router.classify(state["query"])
        return {
            "iterations": _bump(state),
            "intent": decision.intent,
            "intent_source": decision.source,
            "router_latency_ms": decision.latency_ms,
            "route": decision.intent,
        }

    def metadata_lookup(self, state: GraphState) -> dict:
        """`metadata` intent: ACL-scoped Postgres lookup. Hits become normal
        context chunks; no hits → the graph falls back to retrieval."""
        from app.retrieval.metadata_lookup import lookup_documents

        allowed = _uuids(state.get("allowed_collection_ids", []))
        chunks: list[dict] = []
        if allowed:
            try:
                with self.session_factory() as session:
                    chunks = lookup_documents(session, allowed, state["query"])
            except Exception as exc:  # noqa: BLE001 - degrade to retrieval
                logger.warning("metadata lookup failed: %s", exc)
        return {"iterations": _bump(state), "chunks": chunks}

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
        # Visual intent: ColQwen2 page retrieval runs ALONGSIDE the text-hybrid
        # search (spec: per-intent fusion). Degrades to [] without a GPU host.
        page_hits: list[dict] = []
        if state.get("intent") == "visual" and allowed:
            page_hits = [
                {"point_id": str(p.point_id), "document_id": str(p.document_id),
                 "collection_id": str(p.collection_id), "page_number": p.page_number,
                 "image_uri": p.image_uri, "file_name": p.file_name,
                 "score": p.score}
                for p in self.visual.search(allowed, query)
            ]
        elapsed = (time.perf_counter() - t0) * 1000
        return {"iterations": _bump(state),
                "retrieval_latency_ms": elapsed,
                "page_hits": page_hits,
                "chunks": [
            {"chunk_id": str(c.chunk_id), "document_id": str(c.document_id),
             "collection_id": str(c.collection_id), "chunk_type": c.chunk_type,
             "page_number": c.page_number, "section_title": c.section_title,
             "content": c.content, "score": c.score, "file_name": c.file_name,
             "image_uri": c.image_uri}
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
        from app.context import assemble

        # The assembler is the last gate — ACL re-check (defense in depth),
        # hard token budget, fused ordering. Page images are resolved to base64
        # only when the served model can consume them (llm_multimodal, Phase 4);
        # for a text-only model that would be dead MinIO I/O every visual turn.
        allowed = _uuids(state.get("allowed_collection_ids", []))
        assembled = assemble(
            state.get("chunks", []), state.get("page_hits", []), allowed,
            max_images=_settings.context_max_images if _settings.llm_multimodal else 0)

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
            state["query"], assembled.blocks,
            on_token=writer if callable(writer) else None,
            history=history,
            images=[img.b64 for img in assembled.images],
        )
        elapsed = (time.perf_counter() - t0) * 1000
        # Citations come ONLY from [n] markers the model actually wrote, mapped
        # against the exact packed context (not the raw retrieval set).
        citations = extract_citations(answer, assembled.packed_chunks)
        return {"iterations": _bump(state), "answer": answer,
                "citations": citations, "generation_latency_ms": elapsed,
                "context_tokens": assembled.token_count,
                "context_images": len(assembled.images)}

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
                    # Permission component of the cache key (Phase 3): the
                    # asker's FULL scope, not just the answer's sources.
                    requester_scope=_uuids(state.get("allowed_collection_ids", [])),
                    # Persist the rich citations so a cache hit stays verifiable
                    # (source-preview panel needs the passage + figure, not just ids).
                    citations=state.get("citations", []),
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
