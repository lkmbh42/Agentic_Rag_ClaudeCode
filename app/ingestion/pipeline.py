"""Dispatch a file to its parser and produce finalized chunks.

Phase 2: PDF/DOCX/PPTX/XLSX go through the Docling layout-aware parser and the
semantic chunker (`build_chunks_v2`); plain-text types (txt/md/html/csv) and
standalone images keep the legacy parser+chunker. `PARSER_BACKEND=legacy`
forces the old path for rollback (pptx has no legacy parser and will reject).

Figure elements from Docling carry cropped PNG bytes in metadata; a
`figure_sink` callback (the MinIO uploader, wired by the indexer) converts
them to an `image_uri`. The bytes are ALWAYS stripped before chunk building so
binary data never reaches Postgres/Qdrant payloads.
"""

from __future__ import annotations

from collections.abc import Callable

from app.config import get_settings
from app.ingestion import filetype as ft
from app.ingestion.chunker import build_chunks_v2
from app.ingestion.chunking import build_chunks
from app.ingestion.normalize import strip_repeated_boilerplate
from app.ingestion.parsers import image as image_parser
from app.ingestion.parsers import office, pdf, text
from app.ingestion.types import ChunkData, ParsedElement
from app.models.enums import ChunkType

_settings = get_settings()

_PARSERS = {
    ft.PDF: pdf.parse_pdf,
    ft.DOCX: office.parse_docx,
    ft.XLSX: office.parse_xlsx,
    ft.CSV: office.parse_csv,
    ft.TXT: text.parse_txt,
    ft.MD: text.parse_markdown,
    ft.HTML: text.parse_html,
    ft.IMAGE: image_parser.parse_image,
}

_DOCLING_TYPES = {ft.PDF, ft.DOCX, ft.PPTX, ft.XLSX}

FigureSink = Callable[[ParsedElement], str | None]


def _use_docling(file_type: str) -> bool:
    return _settings.parser_backend == "docling" and file_type in _DOCLING_TYPES


def parse(data: bytes, file_type: str) -> list[ParsedElement]:
    if _use_docling(file_type):
        from app.ingestion.docling_parser import parse_docling

        return parse_docling(data, file_type)
    parser = _PARSERS.get(file_type)
    if parser is None:
        raise ValueError(f"No parser for file type {file_type!r} "
                         f"(backend={_settings.parser_backend})")
    return parser(data)


def _denoise(elements: list[ParsedElement]) -> list[ParsedElement]:
    """Strip repeated headers/footers across text pages before chunking."""
    text_pages = [e for e in elements if e.kind == ChunkType.TEXT and e.page]
    if len(text_pages) >= 3:
        cleaned = strip_repeated_boilerplate([e.content for e in text_pages])
        for el, new in zip(text_pages, cleaned):
            el.content = new
    return elements


def _resolve_figures(elements: list[ParsedElement],
                     figure_sink: FigureSink | None) -> None:
    """Upload figure crops via the sink (→ image_uri) and ALWAYS strip the raw
    bytes, so no binary blob can leak into chunk metadata."""
    for el in elements:
        if "image_png" not in el.metadata:
            continue
        uri = figure_sink(el) if figure_sink is not None else None
        el.metadata.pop("image_png", None)
        if uri:
            el.metadata["image_uri"] = uri


def run_pipeline(data: bytes, file_type: str,
                 figure_sink: FigureSink | None = None) -> tuple[list[ChunkData], int]:
    """Return (chunks, page_count)."""
    elements = _denoise(parse(data, file_type))
    pages = {e.page for e in elements if e.page is not None}
    page_count = max(pages) if pages else 1
    if _use_docling(file_type):
        _resolve_figures(elements, figure_sink)
        return build_chunks_v2(elements), page_count
    return build_chunks(elements), page_count
