"""Phase 2 semantic chunker (spec module `ingest/chunker.py`).

Rules (CLAUDE.md Phase 2 task 3):
- TEXT: semantic chunks of 350–600 tokens with 15 % overlap, never merging
  across heading (section) boundaries; splits prefer paragraph breaks.
- TABLE: never flattened to whitespace text. Emitted as
  (a) one GitHub-Markdown chunk prefixed with an auto-generated one-line
      summary (deterministic: dimensions + header names — swap for an LLM
      summary at a later phase if quality demands), and
  (b) row-serialized chunks (`Zeile N: Spalte=Wert, …`) when the table has
      more than `table_row_serialize_threshold` rows, packed to the token
      target so wide tables span multiple row chunks.

Token counting uses a deterministic chars-per-token estimator (≈3.8 chars per
token for the DE/EN corpus mix) so ingestion needs no model file; the
estimator is a seam to swap in the served model's tokenizer during GPU
provisioning without changing chunk logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.ingestion.normalize import normalize_text
from app.ingestion.types import ChunkData, ParsedElement
from app.models.enums import ChunkType

_settings = get_settings()

_CHARS_PER_TOKEN = 3.8


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate (see module docstring)."""
    return max(1, round(len(text) / _CHARS_PER_TOKEN))


# ---------------------------------------------------------------------- tables
@dataclass
class Table:
    """Structured table as emitted by the parser (header optional)."""

    rows: list[list[str]]
    header: list[str] | None = None
    caption: str | None = None

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        widths = [len(r) for r in self.rows] + ([len(self.header)] if self.header else [])
        return max(widths) if widths else 0


def _md_escape(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ").strip()


def table_to_markdown(table: Table) -> str:
    """GitHub-Markdown rendering; structure is preserved, never whitespace-flattened."""
    cols = table.n_cols
    header = table.header or [f"Spalte {i + 1}" for i in range(cols)]
    header = [_md_escape(h) for h in header] + [""] * (cols - len(header))
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join([" --- "] * cols) + "|"]
    for row in table.rows:
        cells = [_md_escape(c) for c in row] + [""] * (cols - len(row))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def table_summary(table: Table, section_title: str | None = None,
                  caption_hint: str | None = None) -> str:
    """Auto-generated one-line summary (DE, deterministic).

    A table's rows are just names and numbers — they share almost no words with a
    natural-language question, so on their own they neither embed near the query
    nor score on a reranker. The summary line is what makes the chunk findable, so
    it must name what the table is *about*: the parser's own caption if it has one,
    else the caption line that sits immediately above the table on the page
    (`caption_hint`), else the broader section. Without this, "wie viele Einwohner
    hat Marburg?" cannot reach a table captioned "Einwohner mit Hauptwohnsitz…"."""
    parts = [f"Tabelle mit {table.n_rows} Zeilen und {table.n_cols} Spalten"]
    if table.caption:
        parts.append(f"({table.caption.strip()})")
    elif caption_hint:
        parts.append(f"({caption_hint.strip()})")
    elif section_title:
        parts.append(f"(Abschnitt: {section_title.strip()})")
    if table.header:
        parts.append("— Spalten: " + ", ".join(h.strip() for h in table.header if h.strip()))
    return " ".join(parts) + "."


def serialize_row(row: list[str], header: list[str] | None, row_no: int) -> str:
    cols = header or [f"Spalte{i + 1}" for i in range(len(row))]
    pairs = ", ".join(
        f"{(cols[i] if i < len(cols) else f'Spalte{i + 1}').strip()}={cell.strip()}"
        for i, cell in enumerate(row) if cell and cell.strip()
    )
    return f"Zeile {row_no}: {pairs}"


def chunk_table(el: ParsedElement, caption_hint: str | None = None) -> list[ChunkData]:
    """Table element → markdown chunk (+ row chunks when large).

    Structured rows are read from `el.metadata['rows']`/`['header']`; when a
    parser supplies only pre-rendered markdown in `el.content`, that is used
    as-is (already structure-preserving) and row serialization is skipped.

    `caption_hint` is the text line directly above the table (see table_summary):
    it makes an otherwise word-less table findable by natural-language queries.
    """
    meta = el.metadata or {}
    rows = meta.get("rows")
    out: list[ChunkData] = []

    if rows:
        table = Table(rows=rows, header=meta.get("header"), caption=meta.get("caption"))
        md = table_to_markdown(table)
        summary = table_summary(table, el.section_title, caption_hint)
    else:
        cap = caption_hint or el.section_title
        summary = f"Tabelle (Abschnitt: {cap})." if cap else "Tabelle."
        md = el.content
        table = None

    base_meta = {k: v for k, v in meta.items() if k not in ("rows", "header")}
    if el.bbox:
        base_meta["bbox"] = list(el.bbox)

    out.append(ChunkData(
        chunk_type=ChunkType.TABLE,
        raw_content=f"{summary}\n\n{md}",
        normalized_content=f"{summary}\n\n{md}",
        chunk_index=0,  # re-indexed by build_chunks_v2
        page_number=el.page,
        section_title=el.section_title,
        source_metadata={**base_meta, "table_repr": "markdown"},
    ))

    if table is not None and table.n_rows > _settings.table_row_serialize_threshold:
        max_chars = int(_settings.chunk_max_tokens * _CHARS_PER_TOKEN)
        buf: list[str] = []
        first_row = 1
        for i, row in enumerate(table.rows, start=1):
            line = serialize_row(row, table.header, i)
            if buf and len(summary) + sum(len(x) + 1 for x in buf) + len(line) > max_chars:
                out.append(_row_chunk(summary, buf, first_row, i - 1, el, base_meta))
                buf, first_row = [], i
            buf.append(line)
        if buf:
            out.append(_row_chunk(summary, buf, first_row, table.n_rows, el, base_meta))
    return out


def _row_chunk(summary: str, lines: list[str], row_from: int, row_to: int,
               el: ParsedElement, base_meta: dict) -> ChunkData:
    body = f"{summary}\n" + "\n".join(lines)
    return ChunkData(
        chunk_type=ChunkType.TABLE,
        raw_content=body,
        normalized_content=body,
        chunk_index=0,
        page_number=el.page,
        section_title=el.section_title,
        source_metadata={**base_meta, "table_repr": "rows",
                         "row_range": [row_from, row_to]},
    )


# ------------------------------------------------------------------------ text
def _pack_paragraphs(paragraphs: list[str]) -> list[str]:
    """Pack paragraphs into 350–600-token windows with 15 % overlap."""
    min_c = int(_settings.chunk_min_tokens * _CHARS_PER_TOKEN)
    max_c = int(_settings.chunk_max_tokens * _CHARS_PER_TOKEN)
    overlap_c = int(max_c * _settings.chunk_overlap_ratio)

    # Hard-split any single paragraph that alone exceeds the max window.
    units: list[str] = []
    for p in paragraphs:
        while len(p) > max_c:
            units.append(p[:max_c])
            p = p[max_c - overlap_c:]
        if p.strip():
            units.append(p)

    chunks: list[str] = []
    buf = ""
    for unit in units:
        candidate = f"{buf}\n\n{unit}" if buf else unit
        if buf and len(candidate) > max_c:
            chunks.append(buf)
            tail = buf[-overlap_c:] if overlap_c else ""
            buf = f"{tail}\n\n{unit}" if tail else unit
        else:
            buf = candidate
    if buf.strip():
        # Merge a tiny tail into the previous chunk when it would undershoot
        # the minimum and the merge stays within ~1.2× max (quality > strictness).
        if chunks and len(buf) < min_c and len(chunks[-1]) + len(buf) < max_c * 1.2:
            chunks[-1] = f"{chunks[-1]}\n\n{buf}"
        else:
            chunks.append(buf)
    return chunks


def chunk_text_run(run: list[ParsedElement]) -> list[ChunkData]:
    """One same-section run of text elements → semantic chunks."""
    section = run[0].section_title
    page_for: list[tuple[int, int | None]] = []  # (char offset, page)
    parts: list[str] = []
    offset = 0
    for el in run:
        normalized = normalize_text(el.content)
        if not normalized:
            continue
        page_for.append((offset, el.page))
        parts.append(normalized)
        offset += len(normalized) + 2

    text = "\n\n".join(parts)
    if not text.strip():
        return []

    paragraphs = [p for p in (s.strip() for s in text.split("\n\n")) if p]
    out: list[ChunkData] = []
    consumed = 0
    for piece in _pack_paragraphs(paragraphs):
        # Attribute the chunk to the page where its window begins.
        page = None
        for off, pg in page_for:
            if off <= consumed:
                page = pg
        out.append(ChunkData(
            chunk_type=ChunkType.TEXT,
            raw_content=piece,
            normalized_content=piece,
            chunk_index=0,
            page_number=page,
            section_title=section,
            source_metadata={},
        ))
        consumed += max(1, len(piece) - int(len(piece) * _settings.chunk_overlap_ratio))
    return out


# ------------------------------------------------------------------- dispatch
_PASSTHROUGH = {ChunkType.IMAGE, ChunkType.CHART, ChunkType.DIAGRAM,
                ChunkType.FORM, ChunkType.OCR}

_CAPTION_HINT_MAX = 160


def _caption_hint(el: ParsedElement | None) -> str | None:
    """The caption/title to carry onto a following table or figure: the first
    line of the nearest preceding text, kept short so it names the visual without
    diluting its embedding with a whole paragraph. None when there's no usable
    text or it's too long to be a caption."""
    if el is None:
        return None
    line = (el.content or "").strip().splitlines()[0].strip() if (el.content or "").strip() else ""
    if not line or len(line) > _CAPTION_HINT_MAX:
        return None
    return line


def build_chunks_v2(elements: list[ParsedElement]) -> list[ChunkData]:
    """Docling-path chunk builder: heading-bounded semantic text chunks,
    structure-preserving table chunks, visual elements passed through."""
    out: list[ChunkData] = []
    run: list[ParsedElement] = []
    last_text: ParsedElement | None = None  # nearest text above a table/figure

    def flush() -> None:
        nonlocal run
        if run:
            out.extend(chunk_text_run(run))
            run = []

    for el in elements:
        if el.kind == ChunkType.TEXT:
            # A heading change closes the current semantic window (spec:
            # respect heading boundaries).
            if run and el.section_title != run[0].section_title:
                flush()
            run.append(el)
            last_text = el
            continue
        flush()
        # The line directly above a table/figure is almost always its caption or
        # title; carry it into the chunk so a word-less table/image is reachable
        # by a natural-language query (see table_summary). Only used as a caption
        # when the element carries no caption of its own.
        caption_hint = _caption_hint(last_text)
        if el.kind == ChunkType.TABLE:
            out.extend(chunk_table(el, caption_hint))
        elif el.kind in _PASSTHROUGH:
            normalized = normalize_text(el.content) or el.content
            has_caption = bool((el.metadata or {}).get("caption"))
            if caption_hint and not has_caption and caption_hint not in normalized:
                normalized = f"{caption_hint}\n\n{normalized}"
            out.append(ChunkData(
                chunk_type=el.kind,
                raw_content=el.content,
                normalized_content=normalized,
                chunk_index=0,
                page_number=el.page,
                section_title=el.section_title,
                source_metadata={**el.metadata,
                                 **({"bbox": list(el.bbox)} if el.bbox else {})},
            ))
        last_text = None  # consumed — don't attach it to a later, unrelated element
    flush()

    for i, chunk in enumerate(out):
        chunk.chunk_index = i
    return out
