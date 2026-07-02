"""Plain text, Markdown, and HTML parsers."""

from __future__ import annotations

import re

from app.ingestion.types import ParsedElement
from app.models.enums import ChunkType

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_txt(data: bytes) -> list[ParsedElement]:
    return [ParsedElement(kind=ChunkType.TEXT, content=_decode(data), page=None)]


def parse_markdown(data: bytes) -> list[ParsedElement]:
    """Group content under its nearest heading so chunks carry a section title."""
    text = _decode(data)
    elements: list[ParsedElement] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            elements.append(
                ParsedElement(kind=ChunkType.TEXT, content=body, section_title=section)
            )
        buf.clear()

    for line in text.split("\n"):
        m = _MD_HEADING.match(line)
        if m:
            flush()
            section = m.group(2).strip()
        else:
            buf.append(line)
    flush()
    return elements or [ParsedElement(kind=ChunkType.TEXT, content=text)]


def parse_html(data: bytes) -> list[ParsedElement]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode(data), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    elements: list[ParsedElement] = []

    # Tables become their own elements (Markdown-rendered).
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            elements.append(ParsedElement(kind=ChunkType.TABLE, content="\n".join(rows)))
        table.decompose()

    body_text = soup.get_text(separator="\n")
    if body_text.strip():
        elements.insert(0, ParsedElement(kind=ChunkType.TEXT, content=body_text))
    return elements or [ParsedElement(kind=ChunkType.TEXT, content="")]
