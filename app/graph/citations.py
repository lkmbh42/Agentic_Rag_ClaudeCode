"""Citation extraction — the anti-fabrication guard.

Citations are derived from the [n] markers the generator actually wrote, mapped
back to the retrieved chunks. Consequences:
  - a chunk that wasn't referenced is never cited;
  - an out-of-range marker (e.g. [9] when 3 chunks exist) is dropped, so the
    model cannot fabricate a source;
  - the safe "insufficient evidence" answer cites nothing.
"""

from __future__ import annotations

import re

from app.graph.state import INSUFFICIENT_ANSWER

_CITE = re.compile(r"\[(\d+)\]")


def extract_citations(answer: str, chunks: list[dict]) -> list[dict]:
    if not answer or answer.strip() == INSUFFICIENT_ANSWER:
        return []
    markers = sorted({int(m) for m in _CITE.findall(answer)})
    citations: list[dict] = []
    for n in markers:
        if 1 <= n <= len(chunks):  # drop fabricated / out-of-range markers
            c = chunks[n - 1]
            citations.append({
                "marker": n,
                "document_id": c["document_id"],
                "chunk_id": c["chunk_id"],
                "page_number": c.get("page_number"),
                "chunk_type": c.get("chunk_type"),
                "file_name": c.get("file_name"),
                "section_title": c.get("section_title"),
                # The exact passage the model was given for this source — powers the
                # UI's source-preview panel so a user can verify the answer against
                # what was actually retrieved, not just take it on faith.
                "content": c.get("content"),
                # Phase 4: lets the UI render a figure-crop thumbnail through
                # the ACL-checked /media endpoint (None for plain text chunks).
                "image_uri": c.get("image_uri"),
            })
    return citations
