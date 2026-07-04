"""Context assembler tests (Phase 3 DoD: budgets hold under adversarial
long-context input; ACL re-check is absolute)."""

from __future__ import annotations

import base64
import logging
import uuid

from app.context import assemble
from app.ingestion.chunker import estimate_tokens

COLL = uuid.uuid4()
OTHER_COLL = uuid.uuid4()


def _chunk(content: str, coll=COLL) -> dict:
    return {
        "chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()),
        "collection_id": str(coll), "chunk_type": "text", "page_number": 1,
        "section_title": None, "content": content, "score": 1.0,
        "file_name": "doc.pdf",
    }


def _page(coll=COLL, uri=None) -> dict:
    doc = uuid.uuid4()
    return {
        "point_id": str(uuid.uuid4()), "document_id": str(doc),
        "collection_id": str(coll), "page_number": 2,
        "image_uri": uri or f"s3://pages/{doc}/2.png",
        "file_name": "doc.pdf", "score": 0.9,
    }


class FakeStore:
    def __init__(self, missing=False):
        self.missing = missing
        self.gets = 0

    def get(self, uri):
        self.gets += 1
        if self.missing:
            raise FileNotFoundError(uri)
        return b"png-bytes"


# ------------------------------------------------------------- token budget
def test_token_budget_holds_under_adversarial_volume():
    # 200 chunks x ~500 tokens >> any budget.
    chunks = [_chunk("wort " * 2000) for _ in range(200)]
    out = assemble(chunks, [], {COLL}, token_budget=1000)
    assert out.packed_chunks, "some context must survive"
    assert out.token_count <= 1000
    assert out.dropped_budget > 0
    assert len(out.blocks) == len(out.packed_chunks)


def test_single_oversized_block_is_truncated_not_starved():
    huge = _chunk("x" * 100_000)
    out = assemble([huge], [], {COLL}, token_budget=500)
    assert len(out.packed_chunks) == 1
    assert estimate_tokens(out.blocks[0]) <= 500
    assert out.blocks[0]  # non-empty
    # The truncated content is what citations refer to.
    assert out.packed_chunks[0]["content"] == out.blocks[0]


def test_packing_respects_fused_order():
    first, second = _chunk("erster"), _chunk("zweiter")
    out = assemble([first, second], [], {COLL})
    assert out.blocks == ["erster", "zweiter"]


# ------------------------------------------------------------- image budget
def test_image_cap_at_config_maximum():
    pages = [_page() for _ in range(10)]
    store = FakeStore()
    out = assemble([], pages, {COLL}, object_store=store, max_images=4)
    assert len(out.images) == 4
    assert store.gets == 4, "no MinIO reads beyond the image budget"
    assert out.dropped_budget == 6
    assert out.images[0].b64 == base64.b64encode(b"png-bytes").decode("ascii")


def test_unreadable_image_is_skipped_not_fatal():
    out = assemble([], [_page()], {COLL}, object_store=FakeStore(missing=True))
    assert out.images == []


def test_max_images_zero_never_touches_the_store():
    store = FakeStore()
    out = assemble([_chunk("text")], [_page()], {COLL},
                   object_store=store, max_images=0)
    assert store.gets == 0
    assert out.images == []
    assert out.blocks == ["text"]


# ------------------------------------------------------------ ACL re-check
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


def test_acl_recheck_drops_foreign_scope_and_screams():
    good, bad = _chunk("ok"), _chunk("leak", coll=OTHER_COLL)
    bad_page = _page(coll=OTHER_COLL)
    # Explicit handler on the assembler logger — the CRITICAL scream is part of
    # the contract (Rule 5 violation visibility), so assert it directly.
    capture = _Capture()
    assembler_logger = logging.getLogger("rag.context.assembler")
    assembler_logger.addHandler(capture)
    try:
        out = assemble([good, bad], [bad_page], {COLL}, object_store=FakeStore())
    finally:
        assembler_logger.removeHandler(capture)
    assert [c["content"] for c in out.packed_chunks] == ["ok"]
    assert out.images == []
    assert out.dropped_acl == 2
    criticals = [r for r in capture.records if r.levelno == logging.CRITICAL]
    assert len(criticals) == 2
    assert all("Rule 5" in r.getMessage() for r in criticals)


def test_empty_input_yields_empty_context():
    out = assemble([], [], {COLL})
    assert out.blocks == [] and out.images == [] and out.token_count == 0
