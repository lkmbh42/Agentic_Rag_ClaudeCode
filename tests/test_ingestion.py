"""Ingestion DoD (part 1): each sample document produces the correct chunk types."""

from __future__ import annotations

import os

import pytest

from app.ingestion import filetype
from app.ingestion.pipeline import run_pipeline
from app.models.enums import ChunkType

# (filename, chunk type that MUST appear in the output)
CASES = [
    ("normal.pdf", ChunkType.TEXT),
    # Docling path (Phase 2): scanned pages OCR into real TEXT chunks instead
    # of the legacy OCR-marker type.
    ("scanned.pdf", ChunkType.TEXT),
    ("table.pdf", ChunkType.TABLE),
    ("chart.pdf", ChunkType.IMAGE),   # figure crop; VLM captioning replaces content in P2.5
    ("sample.csv", ChunkType.TABLE),
    ("sample.docx", ChunkType.TEXT),
    ("sample.xlsx", ChunkType.TABLE),
]


@pytest.mark.parametrize("filename,expected_type", CASES)
def test_sample_produces_expected_chunk_type(samples_dir, filename, expected_type):
    with open(os.path.join(samples_dir, filename), "rb") as fh:
        data = fh.read()
    ft = filetype.detect(filename, data)
    chunks, page_count = run_pipeline(data, ft)

    assert chunks, f"{filename} produced no chunks"
    assert page_count >= 1
    types = {c.chunk_type for c in chunks}
    assert expected_type in types, f"{filename}: expected {expected_type} in {types}"


def test_docx_has_both_text_and_table(samples_dir):
    with open(os.path.join(samples_dir, "sample.docx"), "rb") as fh:
        data = fh.read()
    chunks, _ = run_pipeline(data, filetype.detect("sample.docx", data))
    types = {c.chunk_type for c in chunks}
    assert {ChunkType.TEXT, ChunkType.TABLE} <= types


def test_unsupported_type_rejected():
    with pytest.raises(ValueError):
        filetype.detect("evil.exe", b"MZ\x90\x00")


@pytest.mark.parametrize("hostile,expected", [
    ("../../escape.txt", "escape.txt"),
    ("..\\..\\escape.txt", "escape.txt"),
    ("/etc/cron.d/evil", "evil"),
    ("C:\\Windows\\evil.bat", "evil.bat"),
    ("..", "upload.bin"),
    ("", "upload.bin"),
    ("report.pdf", "report.pdf"),
])
def test_safe_filename_strips_path_components(hostile, expected):
    from app.ingestion.storage import safe_filename

    assert safe_filename(hostile) == expected


def test_save_document_cannot_escape_document_dir(tmp_path, monkeypatch):
    """Regression: a client-controlled filename with path components must land
    inside the per-document directory, never outside the storage root."""
    import uuid as _uuid

    from app.ingestion import storage

    monkeypatch.setattr(storage._settings, "storage_dir", str(tmp_path))
    doc_id = _uuid.uuid4()
    path = storage.save_document(doc_id, "../../escape.txt", b"data")

    inside = os.path.realpath(os.path.join(str(tmp_path), str(doc_id)))
    assert os.path.realpath(path).startswith(inside)
    assert storage.read_document(doc_id, "../../escape.txt") == b"data"
    assert not (tmp_path.parent / "escape.txt").exists()
