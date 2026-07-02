"""Text normalization: whitespace, de-hyphenation, boilerplate removal."""

from __future__ import annotations

import re
from collections import Counter

_WS = re.compile(r"[ \t ]+")
_MULTINEWLINE = re.compile(r"\n{3,}")
# Word split across a line break: "inter-\nnal" -> "internal".
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    # Collapse intra-line whitespace but preserve paragraph breaks.
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text.strip()


def strip_repeated_boilerplate(page_texts: list[str], threshold: float = 0.6) -> list[str]:
    """Remove headers/footers/page numbers that repeat across most pages.

    A short line appearing on >= threshold fraction of pages is treated as
    boilerplate and dropped. Returns cleaned per-page texts.
    """
    if len(page_texts) < 3:
        return page_texts

    counts: Counter[str] = Counter()
    for txt in page_texts:
        seen = {ln.strip() for ln in txt.split("\n") if ln.strip()}
        for ln in seen:
            counts[ln] += 1

    n = len(page_texts)
    boilerplate = {
        ln for ln, c in counts.items()
        if c / n >= threshold and len(ln) <= 80
    }
    if not boilerplate:
        return page_texts

    cleaned = []
    for txt in page_texts:
        kept = [ln for ln in txt.split("\n") if ln.strip() not in boilerplate]
        cleaned.append("\n".join(kept))
    return cleaned
