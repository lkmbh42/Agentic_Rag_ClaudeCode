"""OCR helper (degraded visual path). Wraps pytesseract defensively so a bad
image never crashes ingestion."""

from __future__ import annotations

import logging

logger = logging.getLogger("rag.ingestion.ocr")


def ocr_image(image) -> str:
    """Run OCR on a PIL image, returning extracted text ('' on failure)."""
    try:
        import pytesseract

        return pytesseract.image_to_string(image).strip()
    except Exception as exc:  # noqa: BLE001 - OCR must never break the pipeline
        logger.warning("OCR failed: %s", exc)
        return ""
