"""Context assembler (Phase 3): the LAST gate before the generator.

Consumes the RRF-fused candidates (text/table/figure/metadata chunks + page
hits, app/retrieval/fusion.py) and produces exactly what the generator may see:

- **ACL re-verification (defense in depth, spec):** any candidate whose
  `collection_id` is not in the requester's allowed set is dropped and logged
  CRITICAL. Rule 5 filters inside every store query, so a drop here means a
  Rule 5 bug upstream — the answer still must not leak.
- **Hard token budget:** text blocks are packed in fused order until
  `context_token_budget` is exhausted (same deterministic estimator as the
  chunker). An oversized first block is truncated to the budget rather than
  starving the generator of all context.
- **Image budget:** at most `context_max_images` page images (spec: ≤4).
  MinIO `s3://` URIs are resolved to base64 ONLY here — no upstream component
  ever handles image bytes, and images are never persisted into graph state
  (the checkpointer stores state; base64 pages would bloat every turn).
- **Citations:** `packed_chunks` is the exact, ordered list the generator's
  [n] markers refer to — extract_citations() maps against it 1:1.

The generator consumes `blocks` today (text model); Phase 4 hands `images` to
the VLM in the same call. Building and testing the budgets now is a Phase 3
DoD item (adversarial long-context test).
"""

from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass, field

from app.config import get_settings
from app.ingestion.chunker import estimate_tokens
from app.retrieval.fusion import KIND_PAGE, rrf_merge

logger = logging.getLogger("rag.context.assembler")
_settings = get_settings()


@dataclass
class AssembledImage:
    document_id: str
    page_number: int
    image_uri: str
    b64: str
    file_name: str | None = None


@dataclass
class AssembledContext:
    blocks: list[str] = field(default_factory=list)  # generator contexts, [n]-ordered
    packed_chunks: list[dict] = field(default_factory=list)  # citation source of truth
    images: list[AssembledImage] = field(default_factory=list)
    token_count: int = 0
    dropped_acl: int = 0
    dropped_budget: int = 0


def _acl_ok(item: dict, allowed: set[str]) -> bool:
    return str(item.get("collection_id")) in allowed


def _truncate_to_budget(text: str, budget_tokens: int) -> str:
    # The estimator is chars-per-token linear, so invert it directly.
    from app.ingestion.chunker import _CHARS_PER_TOKEN  # single source of truth

    return text[: int(budget_tokens * _CHARS_PER_TOKEN)]


def assemble(
    chunks: list[dict],
    page_hits: list[dict],
    allowed_collection_ids: set[uuid.UUID],
    *,
    object_store=None,
    token_budget: int | None = None,
    max_images: int | None = None,
) -> AssembledContext:
    token_budget = token_budget or _settings.context_token_budget
    max_images = max_images if max_images is not None else _settings.context_max_images
    allowed = {str(c) for c in allowed_collection_ids}

    out = AssembledContext()
    fused = rrf_merge(chunks or [], page_hits or [])

    for cand in fused:
        item = cand.item
        if not _acl_ok(item, allowed):
            # Should be impossible: every retrieval path filters in-store
            # (Rule 5). Reaching this line is a CRITICAL upstream bug — drop,
            # scream, continue safely.
            logger.critical(
                "ACL re-check dropped %s %s (collection %s not in requester scope) "
                "— Rule 5 violation upstream, report immediately",
                cand.kind, item.get("chunk_id") or item.get("point_id"),
                item.get("collection_id"),
            )
            out.dropped_acl += 1
            continue

        if cand.kind == KIND_PAGE:
            if len(out.images) >= max_images:
                out.dropped_budget += 1
                continue
            b64 = _load_image_b64(item, object_store)
            if b64 is None:
                continue  # unreadable object — never fail the turn over an image
            out.images.append(AssembledImage(
                document_id=str(item["document_id"]),
                page_number=int(item["page_number"]),
                image_uri=str(item["image_uri"]),
                b64=b64,
                file_name=item.get("file_name"),
            ))
            continue

        content = item.get("content", "")
        cost = estimate_tokens(content)
        if out.token_count + cost > token_budget:
            if not out.packed_chunks and content:
                # First block bigger than the whole budget: truncate, don't starve.
                content = _truncate_to_budget(content, token_budget)
                trimmed = dict(item, content=content)
                out.blocks.append(content)
                out.packed_chunks.append(trimmed)
                out.token_count = estimate_tokens(content)
            else:
                out.dropped_budget += 1
            continue
        out.blocks.append(content)
        out.packed_chunks.append(item)
        out.token_count += cost

    return out


def _load_image_b64(item: dict, object_store) -> str | None:
    uri = item.get("image_uri") or ""
    if not uri:
        return None
    try:
        if object_store is None:
            from app.ingestion.object_store import get_object_store

            object_store = get_object_store()
        return base64.b64encode(object_store.get(uri)).decode("ascii")
    except Exception as exc:  # noqa: BLE001 - a missing PNG must not kill the answer
        logger.warning("could not resolve %s to base64: %s", uri, exc)
        return None
