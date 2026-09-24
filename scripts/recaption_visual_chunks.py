"""One-off: retro-fit captions onto already-indexed table/figure chunks.

The chunker now carries the text line directly above a table/figure into that
chunk's embedded content so a word-less table (bare names + numbers) is reachable
by a natural-language query. This backfills that for the EXISTING corpus without
a full re-ingest (which would needlessly re-run CPU VLM captioning): for each
non-text chunk it prepends the nearest preceding text chunk's first line, then
re-embeds and re-upserts the point in Qdrant and updates Postgres.

Idempotent: skips a chunk whose caption is already present in its content.

    docker exec agentic-rag-dev-backend-1 python -m scripts.recaption_visual_chunks
"""
from __future__ import annotations

import psycopg2

from app.config import get_settings
from app.ingestion.qdrant_index import QdrantIndex
from app.retrieval.factory import get_embedder

_CAPTION_MAX = 160
_TEXT = "TEXT"  # chunk_type enum value as stored


def _caption_from(text_content: str | None) -> str | None:
    if not text_content or not text_content.strip():
        return None
    line = text_content.strip().splitlines()[0].strip()
    return line if line and len(line) <= _CAPTION_MAX else None


def main() -> None:
    s = get_settings()
    embedder = get_embedder()
    qindex = QdrantIndex()
    conn = psycopg2.connect(host=s.postgres_host, port=5432, user=s.postgres_user,
                            password=s.postgres_password, dbname=s.postgres_db)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("select distinct document_id from document_chunks")
    doc_ids = [r[0] for r in cur.fetchall()]

    updated = skipped = 0
    for doc_id in doc_ids:
        cur.execute(
            "select id, chunk_type, chunk_index, normalized_content, document_id, "
            "collection_id, chunk_type, page_number, section_title, file_name, file_type "
            "from document_chunks where document_id = %s order by chunk_index", (doc_id,))
        rows = cur.fetchall()
        last_text: str | None = None
        for r in rows:
            (cid, ctype, cidx, content, document_id, collection_id, chunk_type,
             page_number, section_title, file_name, file_type) = r
            if str(ctype).upper().endswith(_TEXT):
                last_text = content
                continue
            caption = _caption_from(last_text)
            last_text = None  # consume: only attach to the immediately-following visual
            if not caption or (content and caption in content):
                skipped += 1
                continue
            new_content = f"{caption}\n\n{content}" if content else caption

            # Postgres
            cur.execute(
                "update document_chunks set normalized_content = %s, updated_at = now() "
                "where id = %s", (new_content, cid))

            # Qdrant: overwrite the same point id with re-embedded vectors + content
            payload = {
                "document_id": str(document_id),
                "collection_id": str(collection_id),
                "chunk_id": str(cid),
                "chunk_type": str(chunk_type).split(".")[-1].lower(),
                "page_number": page_number,
                "section_title": section_title,
                "file_name": file_name,
                "file_type": file_type,
                "content": new_content,
            }
            point = QdrantIndex.make_point(
                cid, embedder.embed_dense(new_content),
                embedder.embed_sparse(new_content), payload)
            qindex.upsert_points([point])
            updated += 1
            print(f"  + [{payload['chunk_type']}] caption={caption[:60]!r}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone. re-captioned {updated} chunk(s), skipped {skipped}.")


if __name__ == "__main__":
    main()
