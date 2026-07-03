"""Docling-based layout-aware parser (Phase 2, spec module `ingest/parser.py`).

Handles PDF (born-digital + scanned via tesseract OCR, `deu+eng`), DOCX, PPTX
and XLSX. Emits ordered `ParsedElement`s typed text | table | figure(IMAGE) |
caption-carrying metadata, with page numbers and bounding-box geometry, ready
for `chunker.build_chunks_v2`.

- Tables come out STRUCTURED (`metadata["rows"]`/`["header"]`) so the chunker
  can render GitHub-MD + row serialization — never flattened.
- Figures carry the cropped PNG bytes in `metadata["image_png"]` plus any
  document caption in `metadata["caption"]`. The pipeline strips the bytes
  before anything reaches Postgres/Qdrant (figures.py uploads them to MinIO
  and replaces them with an `image_uri`).

Air-gap (Rule 2): Docling's layout + TableFormer models are HF artifacts.
In prod they are pre-staged (scripts/stage-docling-models.sh) and loaded via
`settings.docling_artifacts_path`; a missing path there means first use would
download — which the provisioning docs forbid outside the staging step.
"""

from __future__ import annotations

import io
import logging
import threading
from functools import lru_cache

from app.config import get_settings
from app.ingestion import filetype as ft
from app.ingestion.types import ParsedElement
from app.models.enums import ChunkType

logger = logging.getLogger("rag.ingestion.docling")
_settings = get_settings()

_INPUT_NAME = {ft.PDF: "doc.pdf", ft.DOCX: "doc.docx",
               ft.PPTX: "doc.pptx", ft.XLSX: "doc.xlsx"}

# Docling's converter is heavy and not guaranteed thread-safe; the worker is
# single-threaded per process, the lock is protection for future parallelism.
_convert_lock = threading.Lock()


@lru_cache
def _converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_opts = PdfPipelineOptions()
    pdf_opts.do_ocr = True
    pdf_opts.ocr_options = TesseractCliOcrOptions(
        lang=list(_settings.ocr_languages))
    pdf_opts.do_table_structure = True
    pdf_opts.generate_picture_images = True
    pdf_opts.images_scale = 2.0
    if _settings.docling_artifacts_path:
        pdf_opts.artifacts_path = _settings.docling_artifacts_path

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX,
                         InputFormat.PPTX, InputFormat.XLSX],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)},
    )


def _prov(item) -> tuple[int | None, tuple[float, float, float, float] | None]:
    prov = getattr(item, "prov", None) or []
    if not prov:
        return None, None
    p = prov[0]
    bbox = getattr(p, "bbox", None)
    box = (bbox.l, bbox.t, bbox.r, bbox.b) if bbox is not None else None
    return getattr(p, "page_no", None), box


def _table_element(item, doc, section: str | None) -> ParsedElement:
    page, box = _prov(item)
    grid = item.data.grid if item.data is not None else []
    header: list[str] | None = None
    rows: list[list[str]] = []
    for r_idx, row in enumerate(grid):
        cells = [(c.text or "").strip() for c in row]
        if r_idx == 0 and any(getattr(c, "column_header", False) for c in row):
            header = cells
        else:
            rows.append(cells)
    caption = (item.caption_text(doc) or "").strip() or None
    return ParsedElement(
        kind=ChunkType.TABLE,
        content="",  # chunker renders markdown from the structured rows
        page=page,
        section_title=section,
        bbox=box,
        metadata={"rows": rows, **({"header": header} if header else {}),
                  **({"caption": caption} if caption else {})},
    )


def _figure_element(item, doc, section: str | None) -> ParsedElement | None:
    page, box = _prov(item)
    caption = (item.caption_text(doc) or "").strip() or None
    png: bytes | None = None
    try:
        image = item.get_image(doc)
        if image is not None:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            png = buf.getvalue()
    except Exception as exc:  # noqa: BLE001 - a broken crop must not fail the doc
        logger.warning("figure crop failed on page %s: %s", page, exc)
    if png is None and caption is None:
        return None  # nothing usable (decorative artifact)
    return ParsedElement(
        kind=ChunkType.IMAGE,
        # Caption text stands in until VLM captioning replaces it (figures.py).
        content=caption or "",
        page=page,
        section_title=section,
        bbox=box,
        metadata={**({"image_png": png} if png else {}),
                  **({"caption": caption} if caption else {})},
    )


def parse_docling(data: bytes, file_type: str) -> list[ParsedElement]:
    """bytes + canonical type tag → ordered typed elements."""
    from docling.datamodel.base_models import ConversionStatus, DocumentStream
    from docling_core.types.doc import (
        PictureItem,
        SectionHeaderItem,
        TableItem,
        TextItem,
        TitleItem,
    )

    stream = DocumentStream(name=_INPUT_NAME[file_type], stream=io.BytesIO(data))
    with _convert_lock:
        result = _converter().convert(stream, raises_on_error=False)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        errors = "; ".join(str(e.error_message) for e in result.errors[:3])
        raise ValueError(f"docling conversion failed ({result.status}): {errors}")
    doc = result.document

    elements: list[ParsedElement] = []
    section: str | None = None
    for item, _level in doc.iterate_items():
        if isinstance(item, (SectionHeaderItem, TitleItem)):
            section = (item.text or "").strip() or section
            continue
        if isinstance(item, TableItem):
            elements.append(_table_element(item, doc, section))
        elif isinstance(item, PictureItem):
            el = _figure_element(item, doc, section)
            if el is not None:
                elements.append(el)
        elif isinstance(item, TextItem):
            text = (item.text or "").strip()
            if not text:
                continue
            page, box = _prov(item)
            elements.append(ParsedElement(
                kind=ChunkType.TEXT, content=text, page=page,
                section_title=section, bbox=box, metadata={},
            ))
    return elements
