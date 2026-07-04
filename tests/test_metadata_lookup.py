"""Metadata-path tests (Phase 3): ACL-scoped Postgres lookup for the
`metadata` intent. Deterministic — no LLM, no Qdrant."""

from __future__ import annotations

import datetime as dt
import uuid

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.retrieval.metadata_lookup import lookup_documents


def _doc(collection_id, filename, file_type, *, pages=None, uploaded_by=None,
         updated=None) -> Document:
    d = Document(
        collection_id=collection_id, filename=filename, file_type=file_type,
        content_hash=uuid.uuid4().hex, status=DocumentStatus.INDEXED,
        page_count=pages, uploaded_by_id=uploaded_by,
    )
    if updated is not None:
        d.updated_at = updated
    return d


def _now(days_ago: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)


async def _seed_docs(seed, sync_session) -> dict:
    docs = {
        "richtlinie": _doc(seed["coll_a"], "it_richtlinie_de.pdf", "pdf",
                           pages=12, uploaded_by=seed["alice"]["id"],
                           updated=_now(5)),
        "bericht": _doc(seed["coll_a"], "quartalsbericht_2024.pdf", "pdf",
                        pages=30, updated=_now(0)),
        "orgchart": _doc(seed["coll_a"], "orgchart.pptx", "pptx",
                         pages=4, updated=_now(2)),
        "finanz": _doc(seed["coll_b"], "finanzplan.xlsx", "xlsx",
                       updated=_now(1)),
    }
    sync_session.add_all(docs.values())
    sync_session.commit()
    return docs


async def test_acl_filter_is_in_the_query(seed, sync_session):
    await _seed_docs(seed, sync_session)
    hits = lookup_documents(sync_session, {seed["coll_a"]}, "Welche Dokumente gibt es?")
    names = [h["file_name"] for h in hits]
    assert "finanzplan.xlsx" not in names, "coll_b document leaked across ACL"
    assert len(names) == 3

    assert lookup_documents(sync_session, set(), "Welche Dokumente gibt es?") == []


async def test_newest_first_ordering(seed, sync_session):
    await _seed_docs(seed, sync_session)
    hits = lookup_documents(sync_session, {seed["coll_a"]},
                            "Which document was updated most recently?")
    assert hits[0]["file_name"] == "quartalsbericht_2024.pdf"


async def test_filename_narrowing_handles_hyphen_compounds(seed, sync_session):
    await _seed_docs(seed, sync_session)
    hits = lookup_documents(sync_session, {seed["coll_a"]},
                            "Wie viele Seiten hat die IT-Richtlinie?")
    assert [h["file_name"] for h in hits] == ["it_richtlinie_de.pdf"]
    assert "Seiten: 12" in hits[0]["content"]


async def test_file_type_filter(seed, sync_session):
    await _seed_docs(seed, sync_session)
    hits = lookup_documents(sync_session, {seed["coll_a"]},
                            "Welche PPTX-Dateien gibt es?")
    assert [h["file_name"] for h in hits] == ["orgchart.pptx"]


async def test_uploader_and_language_rendering(seed, sync_session):
    await _seed_docs(seed, sync_session)
    de = lookup_documents(sync_session, {seed["coll_a"]},
                          "Wer hat die IT-Richtlinie hochgeladen?")
    assert "Hochgeladen:" in de[0]["content"]
    assert "alice@example.com" in de[0]["content"]

    en = lookup_documents(sync_session, {seed["coll_a"]},
                          "Who uploaded the quarterly report file?")
    assert en and all("Document:" in h["content"] for h in en)
    # No uploader recorded (pre-Phase-3 row without audit backfill) → "unknown".
    bericht = [h for h in en if h["file_name"] == "quartalsbericht_2024.pdf"]
    assert bericht and "by unknown" in bericht[0]["content"]


async def test_chunk_shape_and_limit(seed, sync_session):
    await _seed_docs(seed, sync_session)
    hits = lookup_documents(sync_session, {seed["coll_a"]},
                            "Welche Dokumente gibt es?", limit=2)
    assert len(hits) == 2
    for h in hits:
        assert h["chunk_type"] == "metadata"
        assert h["collection_id"] == str(seed["coll_a"])
        assert h["score"] == 1.0
        assert h["page_number"] is None
