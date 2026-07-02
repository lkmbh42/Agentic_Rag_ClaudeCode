"""Embeddings + reranker service.

Two modes, chosen at runtime:
  - STUB  (dev default): slim image without the model stack; /embed and /rerank
    return 501. Dev retrieval uses the in-process hashing backend instead, so the
    container can stay tiny and healthy.
  - REAL  (prod): set EMBEDDINGS_IMPLEMENTED=true in an image built with
    FlagEmbedding + torch and the BGE-M3 / bge-reranker-v2-m3 weights mounted.
    Loads lazily on first request.

API (consumed by app/retrieval/remote.py):
  POST /embed   {"texts": [...]}  -> {"embeddings": [{"dense": [...],
                                       "sparse": {"indices": [...], "values": [...]}}]}
  POST /rerank  {"query": str, "documents": [...]} -> {"scores": [...]}
"""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
RERANKER = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
DEVICE = os.environ.get("EMBEDDINGS_DEVICE", "cpu")
IMPLEMENTED = os.environ.get("EMBEDDINGS_IMPLEMENTED", "false").lower() == "true"

app = FastAPI(title="Embeddings + Reranker", version="1.0.0")

_lock = threading.Lock()
_embed_model = None
_rerank_model = None


class EmbedRequest(BaseModel):
    texts: list[str]


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_n: int | None = None


def _load_embed():
    global _embed_model
    if _embed_model is None:
        with _lock:
            if _embed_model is None:
                from FlagEmbedding import BGEM3FlagModel

                use_fp16 = DEVICE != "cpu"
                _embed_model = BGEM3FlagModel(MODEL, use_fp16=use_fp16, device=DEVICE)
    return _embed_model


def _load_rerank():
    global _rerank_model
    if _rerank_model is None:
        with _lock:
            if _rerank_model is None:
                from FlagEmbedding import FlagReranker

                use_fp16 = DEVICE != "cpu"
                _rerank_model = FlagReranker(RERANKER, use_fp16=use_fp16, device=DEVICE)
    return _rerank_model


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok", "service": "embeddings", "model": MODEL,
        "reranker": RERANKER, "device": DEVICE, "implemented": IMPLEMENTED,
    }


@app.post("/embed")
async def embed(req: EmbedRequest) -> dict:
    if not IMPLEMENTED:
        raise HTTPException(501, "BGE-M3 not enabled (EMBEDDINGS_IMPLEMENTED=false)")
    model = _load_embed()
    out = model.encode(req.texts, return_dense=True, return_sparse=True, return_colbert_vecs=False)
    embeddings = []
    for dense, lexical in zip(out["dense_vecs"], out["lexical_weights"]):
        indices = [int(k) for k in lexical.keys()]
        values = [float(v) for v in lexical.values()]
        embeddings.append({
            "dense": [float(x) for x in dense],
            "sparse": {"indices": indices, "values": values},
        })
    return {"embeddings": embeddings}


@app.post("/rerank")
async def rerank(req: RerankRequest) -> dict:
    if not IMPLEMENTED:
        raise HTTPException(501, "reranker not enabled (EMBEDDINGS_IMPLEMENTED=false)")
    if not req.documents:
        return {"scores": []}
    model = _load_rerank()
    pairs = [[req.query, doc] for doc in req.documents]
    scores = model.compute_score(pairs, normalize=True)
    if not isinstance(scores, list):
        scores = [scores]
    return {"scores": [float(s) for s in scores]}
