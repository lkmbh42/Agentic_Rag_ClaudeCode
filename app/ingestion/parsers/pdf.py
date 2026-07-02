"""PDF parser — text, tables, images, and OCR for scanned pages.

Engines:
  - PyMuPDF (fitz): per-page text, embedded image extraction, page rasterization.
  - pdfplumber: table extraction (better at ruled tables).
  - pytesseract: OCR for scanned (text-less) pages and embedded figures.

Degraded visual path: embedded figures and scanned pages are OCR'd; figures that
yield no text are stored as IMAGE chunks with the 'not interpreted' marker.
"""

from __future__ import annotations

import io
import logging

from app.ingestion.ocr import ocr_image
from app.ingestion.types import VISUAL_NOT_INTERPRETED, ParsedElement
from app.models.enums import ChunkType

logger = logging.getLogger("rag.ingestion.pdf")
_MIN_IMG_PX = 50  # skip icons/bullets


def _tables_by_page(data: bytes) -> dict[int, list[str]]:
    """Markdown-rendered tables keyed by 0-based page index (best effort)."""
    out: dict[int, list[str]] = {}
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages):
                rendered = []
                for table in page.extract_tables() or []:
                    rows = [
                        "| " + " | ".join("" if c is None else str(c) for c in row) + " |"
                        for row in table
                        if any(c is not None and str(c).strip() for c in row)
                    ]
                    if rows:
                        rendered.append("\n".join(rows))
                if rendered:
                    out[i] = rendered
    except Exception as exc:  # noqa: BLE001 - tables are best-effort
        logger.warning("pdfplumber table extraction failed: %s", exc)
    return out


def parse_pdf(data: bytes) -> list[ParsedElement]:
    import fitz  # PyMuPDF
    from PIL import Image

    elements: list[ParsedElement] = []
    tables = _tables_by_page(data)

    with fitz.open(stream=data, filetype="pdf") as doc:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_no = page_index + 1
            text = page.get_text("text").strip()

            if text:
                elements.append(ParsedElement(kind=ChunkType.TEXT, content=text, page=page_no))
                # Embedded figures on a text page.
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        base = doc.extract_image(xref)
                        pil = Image.open(io.BytesIO(base["image"]))
                        if pil.width < _MIN_IMG_PX or pil.height < _MIN_IMG_PX:
                            continue
                        ocr_text = ocr_image(pil)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("embedded image extraction failed p%s: %s", page_no, exc)
                        continue
                    if ocr_text:
                        elements.append(ParsedElement(
                            kind=ChunkType.OCR, content=ocr_text, page=page_no,
                            metadata={"visual": True, "source": "embedded_image"},
                        ))
                    else:
                        elements.append(ParsedElement(
                            kind=ChunkType.IMAGE, content=VISUAL_NOT_INTERPRETED, page=page_no,
                            metadata={"visual": True, "interpreted": False},
                        ))
            else:
                # Scanned / image-only page: rasterize and OCR.
                try:
                    pix = page.get_pixmap(dpi=200)
                    pil = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_text = ocr_image(pil)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("page render/OCR failed p%s: %s", page_no, exc)
                    ocr_text = ""
                if ocr_text:
                    elements.append(ParsedElement(
                        kind=ChunkType.OCR, content=ocr_text, page=page_no,
                        metadata={"visual": True, "scanned": True},
                    ))
                else:
                    elements.append(ParsedElement(
                        kind=ChunkType.IMAGE, content=VISUAL_NOT_INTERPRETED, page=page_no,
                        metadata={"visual": True, "interpreted": False, "scanned": True},
                    ))

            for md in tables.get(page_index, []):
                elements.append(ParsedElement(kind=ChunkType.TABLE, content=md, page=page_no))

    return elements
