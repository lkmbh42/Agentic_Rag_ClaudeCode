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

# Phase 3 intent router (app/router/): 4 retrieval intents, few-shot DE+EN.
# The examples deliberately cover the traps a small model falls into: table
# questions are TEXT (tables live in the text index), "when/who" about document
# properties is METADATA while "when/who" about document content is TEXT, and
# comparing values inside ONE chart is VISUAL, not multi_doc.
INTENT_ROUTER_SYSTEM = (
    "You classify a user question for a document QA system into exactly ONE "
    "retrieval intent.\n\n"
    "Intents:\n"
    '- "text": the answer is written in the documents — facts, rules, numbers, '
    "definitions, or values from tables.\n"
    '- "visual": the question is about a chart, graph, diagram, figure, image, '
    "photo, drawing, scanned page, or the visual appearance of a page.\n"
    '- "metadata": the question is about document properties — which documents '
    "exist, newest/latest version, upload date, author, file type, page count.\n"
    '- "multi_doc": the question asks to summarize or compare ACROSS several '
    "documents.\n\n"
    'Reply with JSON only: {"intent": "text"} or {"intent": "visual"} or '
    '{"intent": "metadata"} or {"intent": "multi_doc"}.\n\n'
    "Examples:\n"
    'Q: Wie lang müssen Passwörter mindestens sein? -> {"intent": "text"}\n'
    'Q: Welche Werte stehen in der Tabelle der Notfallkontakte? -> {"intent": "text"}\n'
    'Q: When must a security incident be reported? -> {"intent": "text"}\n'
    'Q: Was zeigt das Balkendiagramm auf Seite 3? -> {"intent": "visual"}\n'
    'Q: Which quarter has the highest bar in the revenue chart? -> {"intent": "visual"}\n'
    'Q: Was steht auf dem gescannten Formular? -> {"intent": "visual"}\n'
    'Q: Welches ist die neueste Version der IT-Richtlinie? -> {"intent": "metadata"}\n'
    'Q: Who uploaded the quarterly report, and when? -> {"intent": "metadata"}\n'
    'Q: Wie viele Seiten hat der Arbeitsvertrag? -> {"intent": "metadata"}\n'
    'Q: Vergleiche die Urlaubsregelungen in den beiden Vereinbarungen. -> {"intent": "multi_doc"}\n'
    'Q: Summarize all security policies. -> {"intent": "multi_doc"}\n'
    'Q: Compare the notice periods across all contracts. -> {"intent": "multi_doc"}'
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

# Phase 4 answer contract (CLAUDE.md task 2 + ADR honesty rule). The [n]
# marker protocol is retained as the citation mechanism — it is what
# extract_citations() verifies against the packed context (anti-fabrication);
# the UI renders each [n] as a "doc, Seite N" chip from the citation metadata.
GENERATOR_SYSTEM = (
    "Answer the question using ONLY the numbered context — no outside knowledge; "
    "never reference documents that are not in the context. "
    "Cite each fact with its source number like [1]; only cite contexts that exist. "
    "For numeric values from a chart or figure: state whether the value was read "
    "from the axis labels or visually estimated. If a figure is marked as not "
    "interpreted, say so instead of guessing its contents. "
    "Answer completely: give ALL the relevant details, values, and text the "
    "context provides on the question — not just a title or one-word label. If the "
    "context spells out the answer in full (e.g. the body text of a tip, notice, or "
    "table), reproduce that substance rather than only naming it. "
    "If the context lacks the answer, say so briefly. "
    "Use the conversation so far to resolve follow-up questions."
)

# German system prompt — used when the question is German so the model replies
# in German (a 3B model mirrors the system-prompt language).
GENERATOR_SYSTEM_DE = (
    "Beantworte die Frage AUSSCHLIESSLICH mit dem nummerierten Kontext — kein "
    "externes Wissen; verweise nie auf Dokumente außerhalb des Kontexts. "
    "Antworte auf Deutsch. Belege jede Aussage mit der Quellennummer wie [1]; "
    "zitiere nur vorhandene Kontexte. Bei Zahlenwerten aus einem Diagramm: gib an, "
    "ob der Wert aus der Achsenbeschriftung abgelesen oder visuell geschätzt ist. "
    "Wenn eine Abbildung als nicht interpretiert markiert ist, sage das, statt den "
    "Inhalt zu raten. "
    "Antworte vollständig: nenne ALLE relevanten Angaben, Werte und Textinhalte, "
    "die der Kontext zur Frage liefert — nicht nur einen Titel oder ein Stichwort. "
    "Wenn der Kontext die Antwort ausführlich enthält (z. B. den Fließtext eines "
    "Tipps, Hinweises oder einer Tabelle), gib diesen Inhalt wieder, statt ihn nur "
    "zu benennen. "
    "Wenn der Kontext die Antwort nicht enthält, sage das kurz. "
    "Nutze den bisherigen Gesprächsverlauf für Rückfragen."
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
