"""LLM client interface + an OpenAI-compatible implementation.

This is THE single LLM client module (Phase 1): all LLM traffic — generation,
routing, grading, judging — goes through `OpenAILLM` against whichever backend
`settings.llm_base_url` points at (`settings.llm_backend` names it: vLLM in
prod, Ollama in dev). Both speak the OpenAI chat-completions API, so no code
branches on the backend.

The interface is the seam graph nodes depend on, so tests inject a deterministic
FakeLLM and the real model is never required to exercise graph structure. Methods
are defensive: any LLM error degrades to a safe default rather than crashing the
graph (circuit-breaker philosophy). Request-level availability is a separate
concern: `llm_available()` is a cheap cached reachability probe the gateway uses
to return an explicit 503 instead of degrading silently when the backend is down.

Streaming: `generate(..., on_token=cb)` streams tokens to `cb` as they arrive
(SSE on /chat) and returns the full text.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol
from urllib.parse import urlparse

from app.config import get_settings
from app.graph import prompts
from app.graph.state import ROUTES

logger = logging.getLogger("rag.llm.client")
_settings = get_settings()


class LLMClient(Protocol):
    def route(self, query: str) -> str: ...
    def route_intent(self, query: str) -> str | None: ...
    def plan(self, query: str) -> list[str]: ...
    def rewrite_query(self, query: str) -> str: ...
    def generate(self, query: str, contexts: list[str],
                 on_token: Callable[[str], None] | None = None,
                 history: list[dict] | None = None,
                 images: list[str] | None = None) -> str: ...
    def grade_relevance(self, query: str, contexts: list[str]) -> bool: ...
    def grade_grounded(self, answer: str, contexts: list[str]) -> bool: ...


# ------------------------------------------------------------- availability
def llm_hostport() -> tuple[str, int]:
    """Host/port of the configured backend, for reachability probes."""
    url = urlparse(_settings.llm_base_url)
    host = url.hostname or "localhost"
    port = url.port or (443 if url.scheme == "https" else 80)
    return host, port


_probe_state: tuple[float, bool] = (0.0, False)


def llm_available(ttl_s: float = 5.0, timeout_s: float = 2.0) -> bool:
    """Cheap TCP reachability probe of the LLM backend, cached for `ttl_s` so a
    burst of chat requests doesn't stampede the socket. Used by the gateway to
    fail fast with 503 instead of letting the graph degrade to empty answers."""
    global _probe_state
    checked_at, ok = _probe_state
    now = time.monotonic()
    if now - checked_at < ttl_s:
        return ok
    host, port = llm_hostport()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            ok = True
    except OSError:
        ok = False
    _probe_state = (now, ok)
    return ok


class OpenAILLM:
    """Talks to any OpenAI-compatible server (vLLM prod / Ollama dev)."""

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=_settings.llm_base_url, api_key=_settings.llm_api_key,
            timeout=_settings.llm_request_timeout_s,
        )
        self.model = model or _settings.llm_gen_model
        # Reasoning-model mode (gpt-oss etc.): empty for plain models (vLLM/Qwen),
        # in which case no reasoning param is ever sent and budgets are unchanged.
        self._reasoning = _settings.llm_reasoning_effort.strip().lower()

    def _reasoning_kwargs(self, effort: str | None) -> dict:
        """extra_body carrying reasoning_effort, only when the backend is a
        reasoning model. `effort` overrides the configured level (short calls
        pass 'low'); None uses the configured generation level."""
        if not self._reasoning:
            return {}
        return {"extra_body": {"reasoning_effort": effort or self._reasoning}}

    def _budget(self, base: int, thinking: int = 256) -> int:
        """Give the answer its full token budget PLUS headroom for the reasoning
        stream, which otherwise eats into `base` and truncates the output. No
        change for non-reasoning backends."""
        return base + thinking if self._reasoning else base

    @staticmethod
    def _user_content(user: str, images: list[str] | None):
        """OpenAI message content: plain string without images, content parts
        with them (Phase 4, VL models only — gated by llm_multimodal upstream).
        Images are base64 PNGs from the context assembler; the data-URL form is
        what vLLM's OpenAI-compatible endpoint accepts for local VL serving."""
        if not images:
            return user
        parts: list[dict] = [{"type": "text", "text": user}]
        parts += [{"type": "image_url",
                   "image_url": {"url": f"data:image/png;base64,{b64}"}}
                  for b64 in images]
        return parts

    def _chat(self, system: str, user, max_tokens: int = 512,
              reasoning_effort: str | None = None) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.0, max_tokens=self._budget(max_tokens),
            **self._reasoning_kwargs(reasoning_effort),
        )
        return (resp.choices[0].message.content or "").strip()

    def _chat_stream(self, system: str, user,
                     on_token: Callable[[str], None], max_tokens: int,
                     reasoning_effort: str | None = None) -> str:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.0, max_tokens=self._budget(max_tokens), stream=True,
            **self._reasoning_kwargs(reasoning_effort),
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
            # Short structured calls: keep reasoning minimal so the JSON actually
            # gets emitted within budget instead of being crowded out by thinking.
            out = self._chat(system, user, max_tokens=max_tokens,
                             reasoning_effort="low")
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

    def route_intent(self, query: str) -> str | None:
        """Raw intent label from the model, or None on any failure. Validation
        and the deterministic `text` fallback live in app/router/classifier.py."""
        out = self._json(prompts.INTENT_ROUTER_SYSTEM, query, "intent", None, max_tokens=16)
        return out if isinstance(out, str) else None

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
                 history: list[dict] | None = None,
                 images: list[str] | None = None) -> str:
        system = prompts.generator_system(query)
        user = self._user_content(
            prompts.generator_user(query, contexts, history), images)
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


@lru_cache
def get_class_llm() -> LLMClient:
    """Client bound to the classification model (Qwen2.5-3B role in the model
    manifest) — used by the intent router so routing stays on the small model
    when prod serves a separate large generator."""
    return OpenAILLM(model=_settings.llm_class_model)
