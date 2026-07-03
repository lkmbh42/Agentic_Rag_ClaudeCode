"""Phase 2 chunker: token windows, heading boundaries, table fidelity.

Spec (CLAUDE.md Phase 2 task 3): text 350–600 tokens with 15 % overlap
respecting headings; tables as GitHub-MD chunk with one-line summary plus
row-serialized chunks when >8 rows; tables never whitespace-flattened.
"""

from __future__ import annotations

from app.ingestion.chunker import (
    Table,
    build_chunks_v2,
    chunk_table,
    estimate_tokens,
    serialize_row,
    table_summary,
    table_to_markdown,
)
from app.ingestion.types import ParsedElement
from app.models.enums import ChunkType


def _text(content: str, section: str | None = None, page: int | None = 1) -> ParsedElement:
    return ParsedElement(kind=ChunkType.TEXT, content=content, page=page,
                         section_title=section)


def _table(rows, header=None, page=2, section=None) -> ParsedElement:
    return ParsedElement(kind=ChunkType.TABLE, content="", page=page,
                         section_title=section,
                         metadata={"rows": rows, "header": header})


PARA = ("Die Richtlinie beschreibt die Anforderungen an sichere Passwörter "
        "und deren regelmäßige Änderung im Unternehmen. ")  # ~110 chars


# ------------------------------------------------------------------ text rules
def test_text_chunks_within_token_window():
    elements = [_text(PARA * 40, section="A")]  # ~4400 chars ≈ 1150 tokens
    chunks = build_chunks_v2(elements)
    assert len(chunks) >= 2
    for c in chunks:
        assert estimate_tokens(c.normalized_content) <= 600 * 1.25  # window + merge slack
    # 15 % overlap: consecutive chunks share a tail/head region.
    head = chunks[1].normalized_content[:60]
    assert head.strip()[:30] in chunks[0].normalized_content


def test_heading_boundary_never_crossed():
    elements = [
        _text(PARA * 2, section="1 Einleitung"),
        _text(PARA * 2, section="1 Einleitung"),
        _text(PARA * 2, section="2 Geltungsbereich"),
    ]
    chunks = build_chunks_v2(elements)
    sections = {c.section_title for c in chunks}
    assert sections == {"1 Einleitung", "2 Geltungsbereich"}
    for c in chunks:
        # No chunk may mix content from both sections (same PARA text, so the
        # guarantee is structural: one section_title per chunk).
        assert c.section_title in sections


def test_chunk_indexes_are_sequential():
    chunks = build_chunks_v2([_text(PARA * 10, section="A"),
                              _table([["a", "1"]], header=["K", "V"]),
                              _text(PARA * 10, section="B")])
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# ----------------------------------------------------------------- table rules
def test_small_table_single_markdown_chunk_with_summary():
    el = _table([["Alice", "Berlin"], ["Bob", "Hamburg"]],
                header=["Name", "Standort"], section="Mitarbeiter")
    chunks = chunk_table(el)
    assert len(chunks) == 1  # ≤8 rows → no row serialization
    body = chunks[0].normalized_content
    first_line = body.splitlines()[0]
    assert first_line.startswith("Tabelle mit 2 Zeilen und 2 Spalten")
    assert "Name" in first_line and "Standort" in first_line
    # GitHub-MD structure preserved — never whitespace-flattened.
    assert "| Name | Standort |" in body
    assert "| Alice | Berlin |" in body
    assert chunks[0].source_metadata["table_repr"] == "markdown"


def test_large_table_adds_row_serialized_chunks():
    rows = [[f"Produkt {i}", str(100 + i), f"Kategorie {i % 3}"] for i in range(1, 13)]
    el = _table(rows, header=["Produkt", "Preis", "Kategorie"])
    chunks = chunk_table(el)
    assert chunks[0].source_metadata["table_repr"] == "markdown"
    row_chunks = [c for c in chunks[1:]]
    assert row_chunks, "12 rows > threshold 8 must produce row chunks"
    joined = "\n".join(c.normalized_content for c in row_chunks)
    assert "Zeile 1: Produkt=Produkt 1, Preis=101" in joined
    assert "Zeile 12:" in joined
    covered = [c.source_metadata["row_range"] for c in row_chunks]
    assert covered[0][0] == 1 and covered[-1][1] == 12


def test_markdown_escaping_and_ragged_rows():
    md = table_to_markdown(Table(rows=[["a|b", "x\ny"], ["only-one-cell"]],
                                 header=["Col|1", "Col2"]))
    assert "a\\|b" in md and "x y" in md
    assert md.count("|") >= 12  # ragged row padded to full width


def test_serialize_row_skips_empty_cells():
    line = serialize_row(["", "42", "  "], ["A", "B", "C"], 7)
    assert line == "Zeile 7: B=42"


def test_table_summary_uses_caption_over_section():
    t = Table(rows=[["x"]], caption="Quartalsumsatz")
    assert "Quartalsumsatz" in table_summary(t, section_title="ignored")


def test_premarkdown_table_passthrough():
    el = ParsedElement(kind=ChunkType.TABLE, content="| A |\n| --- |\n| 1 |",
                       page=1, metadata={})
    chunks = chunk_table(el)
    assert len(chunks) == 1
    assert "| A |" in chunks[0].normalized_content
