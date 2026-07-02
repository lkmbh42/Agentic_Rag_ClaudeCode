"""Phase 1 serving migration: single LLM client module + graceful degradation.

The gateway must return an explicit 503 (clear message, retryable) when the LLM
backend is down — never run the graph into silent empty answers. The probe is
backend-agnostic (vLLM prod / Ollama dev), selected only by config.
"""

from __future__ import annotations

import time

from app.llm import client as llm_client


def test_llm_hostport_parses_base_url(monkeypatch):
    monkeypatch.setattr(llm_client._settings, "llm_base_url", "http://vllm:8000/v1")
    assert llm_client.llm_hostport() == ("vllm", 8000)
    monkeypatch.setattr(llm_client._settings, "llm_base_url", "https://gw.internal/v1")
    assert llm_client.llm_hostport() == ("gw.internal", 443)


def test_llm_available_uses_cache_within_ttl(monkeypatch):
    # Seed a fresh negative result; no socket may be opened within the TTL.
    monkeypatch.setattr(llm_client, "_probe_state", (time.monotonic(), False))

    def boom(*a, **kw):  # pragma: no cover - must not be called
        raise AssertionError("socket probe must not run while cache is fresh")

    monkeypatch.setattr(llm_client.socket, "create_connection", boom)
    assert llm_client.llm_available(ttl_s=60.0) is False


def test_llm_available_probes_after_ttl(monkeypatch):
    monkeypatch.setattr(llm_client, "_probe_state", (0.0, False))

    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(llm_client.socket, "create_connection", lambda *a, **kw: _Sock())
    assert llm_client.llm_available(ttl_s=0.0) is True


async def test_chat_returns_503_when_llm_down(client, seed, login, monkeypatch):
    import app.api.chat as chat_api

    monkeypatch.setattr(chat_api, "llm_available", lambda: False)
    headers = await login(seed["alice"]["email"], seed["alice"]["password"])

    r = await client.post("/chat", json={"message": "Hallo"}, headers=headers)
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"]
    assert "ollama" in r.json()["detail"]  # names the configured backend

    r = await client.post("/chat/stream", json={"message": "Hallo"}, headers=headers)
    assert r.status_code == 503


async def test_ready_reports_llm_dependency(client):
    r = await client.get("/health/ready")
    body = r.json()
    assert any(k.startswith("llm:") for k in body["dependencies"])
