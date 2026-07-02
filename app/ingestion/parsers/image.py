"""Standalone image parser (degraded visual path).

OCR the image; if text is found, emit an OCR chunk. Always emit the
'not interpreted' marker so the answer layer can cite it honestly. Real visual
interpretation (chart/diagram understanding) is the VLM full-path upgrade.
"""

from __future__ import annotations

import io

from app.ingestion.ocr import ocr_image
from app.ingestion.types import VISUAL_NOT_INTERPRETED, ParsedElement
from app.models.enums import ChunkType


def parse_image(data: bytes) -> list[ParsedElement]:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        return [ParsedElement(kind=ChunkType.IMAGE,
                              content=f"{VISUAL_NOT_INTERPRETED} (unreadable image: {exc})",
                              page=1)]

    text = ocr_image(img)
    if text:
        return [ParsedElement(
            kind=ChunkType.OCR,
            content=text,
            page=1,
            metadata={"visual": True, "ocr": True},
        )]
    return [ParsedElement(
        kind=ChunkType.IMAGE,
        content=VISUAL_NOT_INTERPRETED,
        page=1,
        metadata={"visual": True, "interpreted": False},
    )]
