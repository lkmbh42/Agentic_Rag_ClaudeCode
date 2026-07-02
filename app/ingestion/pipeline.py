"""Dispatch a file to its parser and produce finalized chunks."""

from __future__ import annotations

from app.ingestion import filetype as ft
from app.ingestion.chunking import build_chunks
from app.ingestion.normalize import strip_repeated_boilerplate
from app.ingestion.parsers import image as image_parser
from app.ingestion.parsers import office, pdf, text
from app.ingestion.types import ChunkData, ParsedElement
from app.models.enums import ChunkType

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


def parse(data: bytes, file_type: str) -> list[ParsedElement]:
    parser = _PARSERS.get(file_type)
    if parser is None:
        raise ValueError(f"No parser for file type {file_type!r}")
    return parser(data)


def _denoise(elements: list[ParsedElement]) -> list[ParsedElement]:
    """Strip repeated headers/footers across text pages before chunking."""
    text_pages = [e for e in elements if e.kind == ChunkType.TEXT and e.page]
    if len(text_pages) >= 3:
        cleaned = strip_repeated_boilerplate([e.content for e in text_pages])
        for el, new in zip(text_pages, cleaned):
            el.content = new
    return elements


def run_pipeline(data: bytes, file_type: str) -> tuple[list[ChunkData], int]:
    """Return (chunks, page_count)."""
    elements = _denoise(parse(data, file_type))
    pages = {e.page for e in elements if e.page is not None}
    page_count = max(pages) if pages else 1
    return build_chunks(elements), page_count
