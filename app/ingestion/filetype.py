"""File-type detection by magic bytes first, extension second."""

from __future__ import annotations

import os

# Canonical internal type tags.
PDF = "pdf"
DOCX = "docx"
PPTX = "pptx"
XLSX = "xlsx"
CSV = "csv"
TXT = "txt"
MD = "md"
HTML = "html"
IMAGE = "image"

_EXT_MAP = {
    ".pdf": PDF,
    ".docx": DOCX,
    ".pptx": PPTX,
    ".xlsx": XLSX,
    ".csv": CSV,
    ".txt": TXT,
    ".md": MD,
    ".markdown": MD,
    ".html": HTML,
    ".htm": HTML,
    ".png": IMAGE,
    ".jpg": IMAGE,
    ".jpeg": IMAGE,
    ".tif": IMAGE,
    ".tiff": IMAGE,
    ".bmp": IMAGE,
}

SUPPORTED = set(_EXT_MAP.values())


def detect(filename: str, data: bytes) -> str:
    """Return a canonical type tag. Raises ValueError for unsupported input."""
    head = data[:8]

    # Unambiguous magic bytes.
    if head.startswith(b"%PDF"):
        return PDF
    if head.startswith(b"\x89PNG") or head[:3] == b"\xff\xd8\xff":
        return IMAGE
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return IMAGE

    ext = os.path.splitext(filename)[1].lower()

    # ZIP-based OOXML (docx/pptx/xlsx) share the PK magic; disambiguate by extension.
    if head[:2] == b"PK\x03\x04":
        if ext in (".docx", ".pptx", ".xlsx"):
            return _EXT_MAP[ext]
        raise ValueError(f"Unsupported OOXML/zip file: {filename}")

    if ext in _EXT_MAP:
        return _EXT_MAP[ext]

    raise ValueError(f"Unsupported file type: {filename!r}")
