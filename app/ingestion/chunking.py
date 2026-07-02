"""Turn parsed elements into finalized, size-bounded chunks.

- Text elements are split on paragraph boundaries into ~target_chars chunks with
  a small overlap, preserving the section title and page they came from.
- Table / image / chart / diagram / form / OCR elements pass through as exactly
  one chunk each (so a table or a visual is never split mid-structure).
"""

from __future__ import annotations

from app.config import get_settings
from app.ingestion.normalize import normalize_text
from app.ingestion.types import ChunkData, ParsedElement
from app.models.enums import ChunkType

_settings = get_settings()
_PASSTHROUGH = {
    ChunkType.TABLE, ChunkType.IMAGE, ChunkType.CHART,
    ChunkType.DIAGRAM, ChunkType.FORM, ChunkType.OCR,
}


def _split_text(text: str, target: int, overlap: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if buf and len(buf) + len(para) + 2 > target:
            chunks.append(buf)
            # Carry an overlap tail for context continuity.
            buf = (buf[-overlap:] + "\n\n" + para) if overlap else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf.strip():
        chunks.append(buf)

    # Hard-split any single oversized paragraph.
    final: list[str] = []
    for c in chunks:
        while len(c) > target * 1.5:
            final.append(c[:target])
            c = c[target - overlap :]
        final.append(c)
    return [c for c in final if c.strip()]


def build_chunks(elements: list[ParsedElement]) -> list[ChunkData]:
    target = _settings.chunk_target_chars
    overlap = _settings.chunk_overlap_chars
    out: list[ChunkData] = []
    idx = 0

    for el in elements:
        if el.kind in _PASSTHROUGH:
            normalized = normalize_text(el.content) if el.kind != ChunkType.TABLE else el.content
            out.append(
                ChunkData(
                    chunk_type=el.kind,
                    raw_content=el.content,
                    normalized_content=normalized,
                    chunk_index=idx,
                    page_number=el.page,
                    section_title=el.section_title,
                    source_metadata={**el.metadata, **({"bbox": list(el.bbox)} if el.bbox else {})},
                )
            )
            idx += 1
            continue

        # Text: normalize then size-split.
        normalized = normalize_text(el.content)
        if not normalized:
            continue
        for piece in _split_text(normalized, target, overlap):
            out.append(
                ChunkData(
                    chunk_type=ChunkType.TEXT,
                    raw_content=piece,
                    normalized_content=piece,
                    chunk_index=idx,
                    page_number=el.page,
                    section_title=el.section_title,
                    source_metadata=dict(el.metadata),
                )
            )
            idx += 1

    return out
