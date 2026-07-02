"""LLM-as-judge scoring (local model; no external APIs).

`chat_fn(system, user) -> str` is the only LLM dependency, so the judge is fully
testable with a deterministic fake. Scores are normalized to 0..1. Two checks are
deterministic (not LLM): citation validity and only-allowed-documents — the
security-relevant ones must not depend on a model's whim.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass

logger = logging.getLogger("rag.eval.judge")
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


@dataclass
class EvalScores:
    faithfulness: float
    answer_relevancy: float
    context_relevancy: float
    retrieval_quality: float
    citation_accuracy: float
    only_allowed_documents: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _score_unit(chat_fn: Callable[[str, str], str], system: str, user: str) -> float:
    """Ask the judge for a 0-10 score; return it normalized to 0..1."""
    try:
        out = chat_fn(system + " Reply with a single integer 0-10.", user)
        m = _NUM.search(out)
        if not m:
            return 0.5
        return max(0.0, min(1.0, float(m.group(1)) / 10.0))
    except Exception as exc:  # noqa: BLE001 - eval must never crash the worker
        logger.warning("judge score failed: %s", exc)
        return 0.5


def evaluate(chat_fn: Callable[[str, str], str], payload: dict) -> EvalScores:
    query = payload.get("query", "")
    answer = payload.get("answer", "")
    contexts = payload.get("contexts", [])
    citations = payload.get("citations", [])
    retrieved = set(payload.get("retrieved_document_ids", []))
    insufficient = payload.get("insufficient", False)

    ctx = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))[:4000]

    # Deterministic security checks.
    only_allowed = all(c.get("document_id") in retrieved for c in citations) if citations else True

    if insufficient or not answer.strip():
        # A correct abstention is faithful and cites nothing falsely.
        faithfulness = 1.0
        citation_accuracy = 1.0
    else:
        faithfulness = _score_unit(
            chat_fn, "Rate how fully the ANSWER is supported ONLY by the CONTEXT.",
            f"CONTEXT:\n{ctx}\n\nANSWER:\n{answer}")
        citation_accuracy = (
            _score_unit(chat_fn, "Rate how accurately the bracketed [n] citations in the "
                        "ANSWER point to context that supports the cited claims.",
                        f"CONTEXT:\n{ctx}\n\nANSWER:\n{answer}")
            if citations else 0.0
        )

    answer_relevancy = _score_unit(
        chat_fn, "Rate how well the ANSWER addresses the QUESTION.",
        f"QUESTION: {query}\n\nANSWER:\n{answer}")
    context_relevancy = _score_unit(
        chat_fn, "Rate how relevant the CONTEXT is to the QUESTION.",
        f"QUESTION: {query}\n\nCONTEXT:\n{ctx}")
    retrieval_quality = _score_unit(
        chat_fn, "Rate how useful the retrieved CONTEXT is for answering the QUESTION.",
        f"QUESTION: {query}\n\nCONTEXT:\n{ctx}")

    return EvalScores(
        faithfulness=faithfulness, answer_relevancy=answer_relevancy,
        context_relevancy=context_relevancy, retrieval_quality=retrieval_quality,
        citation_accuracy=citation_accuracy, only_allowed_documents=only_allowed,
    )
