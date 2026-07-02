"""LLM client interface + an OpenAI-compatible implementation (the vLLM/Ollama
wrapper).

The interface is the seam graph nodes depend on, so tests inject a deterministic
FakeLLM and the real model is never required to exercise graph structure. Methods
are defensive: any LLM error degrades to a safe default rather than crashing the
graph (circuit-breaker philosophy).

Streaming: `generate(..., on_token=cb)` streams tokens to `cb` as they arrive
(SSE on /chat) and returns the full text.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.graph import prompts
from app.graph.state import ROUTES

logger = logging.getLogger("rag.graph.llm")
_settings = get_settings()


class LLMClient(Protocol):
    def route(self, query: str) -> str: ...
    def plan(self, query: str) -> list[str]: ...
    def rewrite_query(self, query: str) -> str: ...
    def generate(self, query: str, contexts: list[str],
                 on_token: Callable[[str], None] | None = None,
                 history: list[dict] | None = None) -> str: ...
    def grade_relevance(self, query: str, contexts: list[str]) -> bool: ...
    def grade_grounded(self, answer: str, contexts: list[str]) -> bool: ...


class OpenAILLM:
    """Talks to any OpenAI-compatible server (Ollama dev / vLLM prod)."""

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=_settings.llm_base_url, api_key=_settings.llm_api_key,
            timeout=_settings.llm_request_timeout_s,
        )
        self.model = model or _settings.llm_gen_model

    def _chat(self, system: str, user: str, max_tokens: int = 512) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.0, max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _chat_stream(self, system: str, user: str,
                     on_token: Callable[[str], None], max_tokens: int) -> str:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.0, max_tokens=max_tokens, stream=True,
        )
        parts: list[str] = []
        for chunk in stream:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                parts.append(delta)
                try:
                    on_token(delta)
                except Exception:  # noqa: BLE001 - a broken sink must not kill generation
                    pass
        return "".join(parts).strip()

    def _json(self, system: str, user: str, key: str, default, max_tokens: int = 64):
        try:
            out = self._chat(system, user, max_tokens=max_tokens)
            # tolerate models that wrap JSON in prose/fences
            start, end = out.find("{"), out.rfind("}")
            if start != -1 and end != -1:
                out = out[start:end + 1]
            return json.loads(out).get(key, default)
        except Exception as exc:  # noqa: BLE001
            logger.warning("json parse failed for %s: %s", key, exc)
            return default

    def route(self, query: str) -> str:
        route = self._json(prompts.ROUTER_SYSTEM, query, "route", "simple_rag", max_tokens=40)
        return route if route in ROUTES else "simple_rag"

    def plan(self, query: str) -> list[str]:
        steps = self._json(prompts.PLANNER_SYSTEM, query, "steps", [query], max_tokens=200)
        return [str(s) for s in steps][:3] or [query]

    def rewrite_query(self, query: str) -> str:
        try:
            return self._chat(prompts.REWRITE_SYSTEM, query, max_tokens=80) or query
        except Exception:  # noqa: BLE001
            return query

    def generate(self, query: str, contexts: list[str],
                 on_token: Callable[[str], None] | None = None,
                 history: list[dict] | None = None) -> str:
        system = prompts.generator_system(query)
        user = prompts.generator_user(query, contexts, history)
        try:
            if on_token is not None:
                return self._chat_stream(system, user, on_token, 700)
            return self._chat(system, user, max_tokens=700)
        except Exception as exc:  # noqa: BLE001
            logger.warning("generate failed: %s", exc)
            return ""

    def grade_relevance(self, query: str, contexts: list[str]) -> bool:
        if not contexts:
            return False
        user = f"Question: {query}\n\nContext:\n{contexts[0][:1500]}"
        # fail open (prefer attempting an answer) on parse failure
        return bool(self._json(prompts.RELEVANCE_SYSTEM, user, "relevant", True, 20))

    def grade_grounded(self, answer: str, contexts: list[str]) -> bool:
        if not answer:
            return False
        user = f"Answer: {answer}\n\nContext:\n{chr(10).join(contexts)[:2000]}"
        return bool(self._json(prompts.GROUNDED_SYSTEM, user, "grounded", True, 20))


@lru_cache
def get_llm() -> LLMClient:
    return OpenAILLM()
