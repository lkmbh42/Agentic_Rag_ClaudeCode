"""Metadata path (Phase 3): `metadata` intent → ACL-scoped Postgres lookup.

Answers questions about document PROPERTIES — which documents exist, newest
version, upload date, uploader ("author"), file type, page count — from
Postgres, not the vector store (spec: "Postgres-filtered lookup first").

Security (Rule 5): the collection filter is in the SQL WHERE clause; documents
outside the requester's scope are never even rows in the result.

The hits are rendered as synthetic `type=metadata` context chunks (DE or EN to
match the question, Rule 8) so the downstream pipeline — generator, citations,
eval — is unchanged. If the lookup matches nothing, the graph falls back to
normal retrieval ("then optional retrieval").

Deterministic by design: filename-token and file-type matching plus
recency ordering. No LLM is involved in the lookup itself.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.graph.prompts import detect_lang
from app.models.collection import Collection
from app.models.document import Document
from app.models.user import User

_settings = get_settings()

_FILE_TYPES = ("pdf", "docx", "pptx", "xlsx", "csv", "txt", "md")
# Query words that are about the ASK, not a filename — never used for matching.
_STOPWORDS = {
    # de
    "das", "der", "die", "und", "oder", "ist", "sind", "wie", "was", "wer", "wann",
    "welche", "welches", "welcher", "viele", "seiten", "hat", "gibt", "eine", "einen",
    "neueste", "neuere", "aktuellste", "version", "fassung", "dokument", "dokumente",
    "datei", "dateien", "sammlung", "hochgeladen", "aktualisiert", "zuletzt", "von",
    # en
    "the", "and", "what", "which", "who", "when", "how", "many", "pages", "does",
    "have", "there", "are", "is", "latest", "newest", "version", "document",
    "documents", "file", "files", "collection", "uploaded", "updated", "recently",
    "most", "author", "type", "list", "all", "available", "week", "this", "was",
}


def _tokens(query: str) -> list[str]:
    words = re.findall(r"[\wäöüß-]+", (query or "").lower())
    # Hyphenated compounds ("IT-Richtlinie") also match their parts, since
    # filenames typically use underscores ("it_richtlinie_de.pdf").
    expanded: list[str] = []
    for w in words:
        expanded.append(w)
        if "-" in w:
            expanded.extend(p for p in w.split("-") if p)
    return [w for w in expanded if len(w) >= 3 and w not in _STOPWORDS
            and w not in _FILE_TYPES]


def _mentioned_types(query: str) -> list[str]:
    q = (query or "").lower()
    return [t for t in _FILE_TYPES if re.search(rf"\b{t}\b", q)]


def _render(doc: Document, collection_name: str, uploader_email: str | None,
            lang: str) -> str:
    pages = doc.page_count if doc.page_count is not None else "?"
    uploaded = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else "?"
    updated = doc.updated_at.strftime("%Y-%m-%d") if doc.updated_at else "?"
    if lang == "de":
        uploader = uploader_email or "unbekannt"
        return (f"Dokument: {doc.filename} | Sammlung: {collection_name} | "
                f"Typ: {doc.file_type} | Seiten: {pages} | "
                f"Status: {doc.status.value} | "
                f"Hochgeladen: {uploaded} von {uploader} | "
                f"Zuletzt aktualisiert: {updated}")
    uploader = uploader_email or "unknown"
    return (f"Document: {doc.filename} | Collection: {collection_name} | "
            f"Type: {doc.file_type} | Pages: {pages} | "
            f"Status: {doc.status.value} | "
            f"Uploaded: {uploaded} by {uploader} | "
            f"Last updated: {updated}")


def lookup_documents(
    session: Session,
    allowed_collection_ids: set[uuid.UUID],
    query: str,
    limit: int | None = None,
) -> list[dict]:
    """Return metadata hits as graph-compatible chunk dicts (newest first).
    Empty list when nothing in scope matches — the caller then falls back to
    normal retrieval."""
    if not allowed_collection_ids:
        return []
    limit = limit or _settings.metadata_max_documents
    lang = detect_lang(query)

    stmt = (
        select(Document, Collection.name, User.email)
        .join(Collection, Collection.id == Document.collection_id)
        .join(User, User.id == Document.uploaded_by_id, isouter=True)
        .where(Document.collection_id.in_(allowed_collection_ids))
        .order_by(Document.updated_at.desc(), Document.created_at.desc())
    )

    types = _mentioned_types(query)
    if types:
        stmt = stmt.where(Document.file_type.in_(types))

    rows = session.execute(stmt).all()

    # Filename/collection keyword narrowing: applied only if it matches
    # something, so "which documents exist?" still lists everything in scope.
    tokens = _tokens(query)
    if tokens:
        narrowed = [
            r for r in rows
            if any(t in r.Document.filename.lower() or t in (r.name or "").lower()
                   for t in tokens)
        ]
        if narrowed:
            rows = narrowed

    out: list[dict] = []
    for row in rows[:limit]:
        doc = row.Document
        out.append({
            "chunk_id": str(doc.id),  # the document itself is the citable unit
            "document_id": str(doc.id),
            "collection_id": str(doc.collection_id),
            "chunk_type": "metadata",
            "page_number": None,
            "section_title": None,
            "content": _render(doc, row.name, row.email, lang),
            "score": 1.0,
            "file_name": doc.filename,
        })
    return out
