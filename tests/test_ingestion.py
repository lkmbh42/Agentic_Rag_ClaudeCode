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
    ("scanned.pdf", ChunkType.OCR),
    ("table.pdf", ChunkType.TABLE),
    ("chart.pdf", ChunkType.IMAGE),   # degraded visual path -> uninterpreted image
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
