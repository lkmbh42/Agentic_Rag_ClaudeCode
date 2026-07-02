"""Shared ingestion dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import ChunkType

VISUAL_NOT_INTERPRETED = "[visual — not interpreted]"


@dataclass
class ParsedElement:
    """A unit emitted by a parser before chunking.

    Text elements are merged/split into size-bounded chunks; table/image/ocr
    elements pass through as one chunk each.
    """

    kind: ChunkType
    content: str
    page: int | None = None
    section_title: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ChunkData:
    """A finalized chunk ready to persist + index."""

    chunk_type: ChunkType
    raw_content: str
    normalized_content: str
    chunk_index: int
    page_number: int | None = None
    section_title: str | None = None
    source_metadata: dict = field(default_factory=dict)
