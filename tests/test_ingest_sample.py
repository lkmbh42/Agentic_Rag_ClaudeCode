"""Phase 2 sampling harness: produces a side-by-side HTML report with page
images and extracted chunks. Marked docling (runs the real parser)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.docling


def test_sampling_report_renders(samples_dir, tmp_path):
    from eval.ingest_sample import TEMPLATE, sample

    sections = sample(Path(samples_dir), n_pages=4, seed=1)
    assert sections, "no pages sampled"
    out = tmp_path / "sample.html"
    out.write_text(TEMPLATE.format(n=len(sections), corpus="samples",
                                   body="\n".join(sections)), encoding="utf-8")
    doc = out.read_text(encoding="utf-8")
    # Side-by-side: page image (data URI) next to extracted chunks.
    assert "data:image/png;base64," in doc
    assert "class=\"extracted\"" in doc
    assert "<section>" in doc
