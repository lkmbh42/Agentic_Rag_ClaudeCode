"""Deterministic fakes for graph tests (no real model required)."""

from __future__ import annotations

import uuid

from app.retrieval.types import RetrievedChunk


class FakeLLM:
    def __init__(self, route="simple_rag", relevant=True, grounded=True,
                 answer="Fake answer [1].", intent="text"):
        self._route, self._relevant, self._grounded, self._answer = route, relevant, grounded, answer
        self._intent = intent

    def route(self, query): return self._route
    def route_intent(self, query): return self._intent
    def plan(self, query): return [query]
    def rewrite_query(self, query): return query + " (rewritten)"

    def generate(self, query, contexts, on_token=None, history=None):
        if on_token is not None:
            for word in self._answer.split(" "):
                on_token(word + " ")
        return self._answer

    def grade_relevance(self, query, contexts): return self._relevant
    def grade_grounded(self, answer, contexts): return self._grounded


class FakeRetriever:
    def search(self, allowed, query, top_k=None, top_n=None):
        if not allowed:
            return []
        coll = next(iter(allowed))
        return [RetrievedChunk(
            chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), collection_id=coll,
            chunk_type="text", page_number=1, section_title=None, score=1.0,
            snippet="ctx", content=f"context about {query}",
        )]


class FakeVisualRetriever:
    def __init__(self, pages=None):
        self._pages = pages or []

    def search(self, allowed, query, top_k=None):
        return self._pages if allowed else []


class FakeCache:
    def __init__(self, hit=None):
        self._hit = hit

    def lookup(self, allowed, query): return self._hit
    def store(self, *a, **k): return uuid.uuid4()
    def ensure_collection(self): pass


class FakeRedis:
    """In-memory stand-in so the eval_queue node never touches the real dev
    Redis (which a running worker would drain into the dev eval_results table)."""

    def __init__(self):
        self.queues: dict[str, list[str]] = {}

    def rpush(self, key, *values):
        q = self.queues.setdefault(key, [])
        q.extend(values)
        return len(q)
