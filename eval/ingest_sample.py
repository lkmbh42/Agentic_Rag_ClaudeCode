"""Ingestion quality sampling harness (Phase 2, spec task 8).

Renders a side-by-side HTML report: each sampled page's rendered image next to
the text / table / figure-caption chunks the pipeline extracted from it, so a
human can rate table fidelity (DoD ≥90 %) and caption usefulness (DoD ≥85 %).

Runs INSIDE the backend/worker image (needs app.* + docling). Samples random
pages across the given documents (or the fixture corpus) directly through the
pipeline — no live backend required.

Usage (in the backend container):
  python eval/ingest_sample.py --corpus eval/fixtures/corpus \
      --pages 30 --out eval/reports/ingest_sample.html
"""

from __future__ import annotations

import argparse
import base64
import html
import random
import sys
from pathlib import Path

from app.ingestion import filetype as ft
from app.ingestion.chunker import build_chunks_v2
from app.ingestion.docling_parser import parse_docling
from app.ingestion.pages import render_pages
from app.models.enums import ChunkType

_DOCLING = {ft.PDF, ft.DOCX, ft.PPTX, ft.XLSX}


def _png_data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _chunk_html(el) -> str:
    kind = el.kind.value
    if el.kind == ChunkType.TABLE and (el.metadata or {}).get("rows"):
        rows = el.metadata["rows"]
        header = el.metadata.get("header")
        thead = ("<tr>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in header) + "</tr>"
                 if header else "")
        body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
            for r in rows)
        return f'<div class="chunk table"><span class="tag">{kind}</span>' \
               f'<table>{thead}{body}</table></div>'
    text = html.escape(el.content or "(empty)")
    return f'<div class="chunk {kind}"><span class="tag">{kind}</span><pre>{text}</pre></div>'


def sample(corpus: Path, n_pages: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    files = sorted(p for p in corpus.iterdir() if p.is_file())
    # Collect (file, page) candidates, then sample.
    sections: list[str] = []
    picked = 0
    rng.shuffle(files)
    for path in files:
        if picked >= n_pages:
            break
        file_type = ft.detect(path.name, path.read_bytes())
        if file_type not in _DOCLING:
            continue
        data = path.read_bytes()
        try:
            elements = parse_docling(data, file_type)
        except Exception as exc:  # noqa: BLE001
            sections.append(f'<h2>{html.escape(path.name)} — PARSE FAILED: '
                            f'{html.escape(str(exc))}</h2>')
            continue
        by_page: dict[int, list] = {}
        for el in elements:
            by_page.setdefault(el.page or 0, []).append(el)

        renders = {rp.page_number: rp.png for rp in render_pages(data)} \
            if file_type == ft.PDF else {}

        pages = sorted(by_page)
        rng.shuffle(pages)
        for page_no in pages:
            if picked >= n_pages:
                break
            img = (f'<img src="{_png_data_uri(renders[page_no])}"/>'
                   if page_no in renders else '<div class="noimg">no render</div>')
            chunks_html = "".join(_chunk_html(el) for el in by_page[page_no])
            sections.append(
                f'<section><h2>{html.escape(path.name)} · Seite {page_no}</h2>'
                f'<div class="cols"><div class="img">{img}</div>'
                f'<div class="extracted">{chunks_html}</div></div></section>')
            picked += 1
    return sections


TEMPLATE = """<!doctype html><meta charset="utf-8">
<title>Ingestion sample</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:1.5rem;background:#f6f7f9}}
 section{{background:#fff;border:1px solid #ddd;border-radius:8px;margin:1rem 0;padding:1rem}}
 .cols{{display:flex;gap:1rem;align-items:flex-start}}
 .img,.extracted{{flex:1;min-width:0;overflow-x:auto}}
 .img img{{max-width:100%;border:1px solid #ccc}}
 .noimg{{color:#999;padding:2rem;text-align:center;border:1px dashed #ccc}}
 .chunk{{border-left:3px solid #bbb;margin:.5rem 0;padding:.25rem .5rem;background:#fafafa}}
 .chunk.table{{border-color:#2a7}}.chunk.image{{border-color:#c72}}
 .chunk.text{{border-color:#69c}}
 .tag{{font-size:.7rem;text-transform:uppercase;color:#666;letter-spacing:.05em}}
 pre{{white-space:pre-wrap;margin:.25rem 0;font-size:.85rem}}
 table{{border-collapse:collapse;font-size:.8rem}}td,th{{border:1px solid #ccc;padding:2px 6px}}
</style>
<h1>Ingestion sampling report</h1>
<p>{n} pages sampled from <code>{corpus}</code> · review table fidelity (≥90%) and
caption usefulness (≥85%).</p>
{body}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--corpus", default="eval/fixtures/corpus")
    ap.add_argument("--pages", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="eval/reports/ingest_sample.html")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    if not corpus.is_dir():
        sys.exit(f"corpus dir not found: {corpus}")
    sections = sample(corpus, args.pages, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.format(n=len(sections), corpus=html.escape(str(corpus)),
                                   body="\n".join(sections)), encoding="utf-8")
    print(f"wrote {out} ({len(sections)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
