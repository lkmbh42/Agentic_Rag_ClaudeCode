"""Prompt templates for the agent's LLM call-sites.

Centralized so prompt changes are reviewable and regression-testable (Phase 7
golden set). The generator prompt enforces context-only answering with [n]
citations and an explicit "insufficient evidence" escape hatch — this is what
makes the DoD (unanswerable -> safe answer, no fabricated citations) achievable.
"""

from __future__ import annotations

import re

from app.graph.state import INSUFFICIENT_ANSWER, ROUTES

# --- lightweight language detection (a weak model obeys a same-language system
# prompt far more reliably than an English "answer in German" instruction) -----
_DE_CHARS = re.compile(r"[äöüßÄÖÜ]")
_DE_WORDS = {
    "der", "die", "das", "und", "ist", "sind", "was", "wie", "mehr", "auf", "mir",
    "den", "dem", "ein", "eine", "nicht", "mit", "für", "von", "zu", "sich", "auch",
    "werden", "wird", "aufgaben", "erkläre", "erklär", "warum", "wer", "welche", "kannst",
}


def detect_lang(text: str) -> str:
    if _DE_CHARS.search(text or ""):
        return "de"
    words = set(re.findall(r"\w+", (text or "").lower()))
    return "de" if len(words & _DE_WORDS) >= 2 else "en"

ROUTER_SYSTEM = (
    "You are a query router for a document QA system. Classify the user question "
    "into exactly one category. Reply with JSON only: {\"route\": \"<category>\"}. "
    f"Categories: {sorted(ROUTES)}."
)

PLANNER_SYSTEM = (
    "Break the question into at most 3 concrete retrieval sub-steps. "
    'Reply with JSON only: {"steps": ["...", "..."]}.'
)

REWRITE_SYSTEM = (
    "The previous retrieval was weak. Rewrite the user question to improve "
    "document retrieval (add synonyms/keywords, remove chit-chat). "
    "Reply with ONLY the rewritten query, no preamble."
)

GENERATOR_SYSTEM = (
    "Answer the question using ONLY the numbered context — no outside knowledge. "
    "Cite each fact with its source number like [1]; only cite contexts that exist. "
    "If the context lacks the answer, say so briefly. "
    "Use the conversation so far to resolve follow-up questions."
)

# German system prompt — used when the question is German so the model replies
# in German (a 3B model mirrors the system-prompt language).
GENERATOR_SYSTEM_DE = (
    "Beantworte die Frage AUSSCHLIESSLICH mit dem nummerierten Kontext — kein "
    "externes Wissen. Antworte auf Deutsch. Belege jede Aussage mit der "
    "Quellennummer wie [1]; zitiere nur vorhandene Kontexte. Wenn der Kontext die "
    "Antwort nicht enthält, sage das kurz. Nutze den bisherigen Gesprächsverlauf "
    "für Rückfragen."
)


def generator_system(query: str) -> str:
    return GENERATOR_SYSTEM_DE if detect_lang(query) == "de" else GENERATOR_SYSTEM

RELEVANCE_SYSTEM = (
    "Decide whether the context is relevant to answering the question. "
    'Reply with JSON only: {"relevant": true|false}.'
)

GROUNDED_SYSTEM = (
    "Decide whether EVERY claim in the answer is supported by the context. "
    "If the answer states it lacks evidence, that counts as grounded. "
    'Reply with JSON only: {"grounded": true|false}.'
)


def format_context(contexts: list[str]) -> str:
    return "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))


def generator_user(query: str, contexts: list[str], history: list[dict] | None = None) -> str:
    convo = ""
    if history:
        turns = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
        convo = f"Conversation so far:\n{turns}\n\n"
    return f"{convo}Context:\n{format_context(contexts)}\n\nQuestion: {query}\n\nAnswer:"
