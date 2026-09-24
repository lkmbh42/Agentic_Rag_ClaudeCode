"""Bulk-upload a folder of documents through the API (no UI needed).

Logs in, resolves a target collection, then uploads every matching file in a
folder via POST /documents/upload — which is the ONLY correct way to ingest
(it creates the Postgres row, saves the file, and queues the indexing job;
dropping a file in the storage volume does none of that). Idempotent: the
backend skips files whose content already exists (content-hash dedupe).

Standalone: stdlib + httpx only, runs from the host against the dev stack.

Usage:
  python scripts/upload_folder.py --dir "C:/my/pdfs"
  python scripts/upload_folder.py --dir ./samples --collection "Sample" --wait
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

# File types the ingestion pipeline accepts (see app/ingestion/filetype.py).
SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md"}


def login(http: httpx.Client, email: str, password: str) -> None:
    r = http.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    http.headers["Authorization"] = f"Bearer {r.json()['access_token']}"


def resolve_collection(http: httpx.Client, wanted: str | None) -> str:
    cols = http.get("/collections").json()
    if not cols:
        sys.exit("No collections you can access. Create one first (admin UI or "
                 "POST /admin/collections), then pass --collection.")
    if wanted:
        for c in cols:  # match by id or name
            if wanted in (c["id"], c.get("name")):
                return c["id"]
        names = ", ".join(f'{c.get("name")!r}' for c in cols)
        sys.exit(f"Collection {wanted!r} not found. Available: {names}")
    print(f"Using collection {cols[0].get('name')!r} ({cols[0]['id']})")
    return cols[0]["id"]


def upload_one(http: httpx.Client, collection_id: str, path: Path) -> dict:
    with path.open("rb") as fh:
        r = http.post("/documents/upload",
                      data={"collection_id": collection_id},
                      files={"file": (path.name, fh)})
    r.raise_for_status()
    return r.json()


def wait_indexed(http: httpx.Client, doc_id: str, timeout_s: int) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = http.get(f"/documents/{doc_id}/ingest-status").json()
        status = (st or {}).get("status")
        if status in ("indexed", "failed"):
            return status
        time.sleep(3)
    return "timeout"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dir", required=True, help="folder of files to upload")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", default="admin@example.com")
    ap.add_argument("--password", default="admin-pass-123")
    ap.add_argument("--collection", default=None,
                    help="collection name or id (default: first accessible)")
    ap.add_argument("--recursive", action="store_true", help="include subfolders")
    ap.add_argument("--wait", action="store_true",
                    help="poll each upload until indexed/failed")
    ap.add_argument("--wait-s", type=int, default=300)
    args = ap.parse_args()

    folder = Path(args.dir)
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    globber = folder.rglob("*") if args.recursive else folder.glob("*")
    files = sorted(p for p in globber if p.is_file() and p.suffix.lower() in SUFFIXES)
    if not files:
        sys.exit(f"No supported files ({', '.join(sorted(SUFFIXES))}) in {folder}")

    http = httpx.Client(base_url=args.base_url, timeout=120)
    login(http, args.email, args.password)
    collection_id = resolve_collection(http, args.collection)

    print(f"Uploading {len(files)} file(s) to {args.base_url} ...")
    uploaded, duplicate, failed = [], 0, 0
    for i, path in enumerate(files, 1):
        try:
            res = upload_one(http, collection_id, path)
        except httpx.HTTPStatusError as exc:
            failed += 1
            detail = exc.response.text[:120]
            print(f"[{i:3}/{len(files)}] FAIL  {path.name} — HTTP "
                  f"{exc.response.status_code}: {detail}")
            continue
        doc = res["document"]
        if res.get("duplicate"):
            duplicate += 1
            print(f"[{i:3}/{len(files)}] dup   {path.name} (already ingested)")
            continue
        uploaded.append(doc["id"])
        tail = ""
        if args.wait:
            tail = " -> " + wait_indexed(http, doc["id"], args.wait_s)
        print(f"[{i:3}/{len(files)}] ok    {path.name} ({doc['id']}){tail}")

    print(f"\nDone: {len(uploaded)} uploaded, {duplicate} duplicates, {failed} failed.")
    if not args.wait and uploaded:
        print("Indexing runs in the background. Check status in the UI, or:")
        print(f"  curl {args.base_url}/documents/<id>/ingest-status -H 'Authorization: Bearer <token>'")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
