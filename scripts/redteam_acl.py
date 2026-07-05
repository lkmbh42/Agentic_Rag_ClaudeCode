"""ACL red-team (Phase 5 §3): attempt cross-tenant retrieval via EVERY path.

Provisions two isolated tenants as admin — user A → collection A, user B →
collection B, disjoint READ grants, a distinct document uploaded and indexed in
each — then, authenticated as user A, tries to reach B's content through every
surface the ACL invariant (Rule 5) must cover:

  1. text search        POST /search                      (docs_text hybrid)
  2. visual pages       POST /search {include_pages}      (docs_pages ColQwen2)
  3. semantic cache     B asks Q, then A asks the same Q   (scope-hash key)
  4. media (MinIO)      GET /media/pages|figures/{Bdoc}/… (object store)
  5. metadata lookup    A chat "welche Dokumente gibt es" (Postgres lookup)
  6. direct object      GET /documents/{Bdoc}, /ingest-status, /documents list

Every probe must be DENIED (empty results / 404 / no B-doc reference). Any leak
is a CRITICAL Rule-5 bypass: the script prints it, writes the report, and exits
non-zero. Standalone (stdlib + httpx), runs from the host against any deployment.

Usage:
  python scripts/redteam_acl.py --base-url http://localhost:8000 \
      --admin-email admin@example.com --admin-password admin-pass-123
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
SAMPLES = REPO / "samples"


@dataclass
class Probe:
    path: str          # which retrieval surface
    description: str
    denied: bool       # True = access correctly denied (PASS)
    detail: str = ""


@dataclass
class Result:
    probes: list[Probe] = field(default_factory=list)

    def add(self, path, description, denied, detail=""):
        self.probes.append(Probe(path, description, denied, detail))
        mark = "DENIED " if denied else "LEAK!! "
        print(f"  [{mark}] {path}: {description}{(' — ' + detail) if detail else ''}", flush=True)

    @property
    def leaks(self):
        return [p for p in self.probes if not p.denied]


class Client:
    def __init__(self, base_url: str, timeout: float):
        self.http = httpx.Client(base_url=base_url, timeout=timeout)
        self.token: str | None = None

    def login(self, email: str, password: str) -> None:
        r = self.http.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def req(self, method: str, path: str, **kw) -> httpx.Response:
        return self.http.request(method, path, headers=self._h(), **kw)


def _provision(admin: Client, tag: str) -> dict:
    """Create dept+collection+user; grant the user READ on the collection."""
    dept = admin.req("POST", "/admin/departments",
                     json={"name": f"redteam-{tag}-{uuid.uuid4().hex[:6]}"}).json()
    coll = admin.req("POST", "/admin/collections",
                     json={"name": f"redteam-{tag}", "department_id": dept["id"]}).json()
    email = f"redteam-{tag}-{uuid.uuid4().hex[:6]}@example.com"
    pw = "redteam-pass-123"
    user = admin.req("POST", "/admin/users",
                     json={"email": email, "password": pw, "role": "user",
                           "department_id": dept["id"]}).json()
    admin.req("POST", "/admin/permissions", json={
        "principal_type": "user", "principal_id": user["id"],
        "resource_type": "collection", "resource_id": coll["id"],
        "access_level": "read",
    }).raise_for_status()
    return {"dept": dept, "coll": coll, "email": email, "password": pw, "user": user}


def _upload_and_index(admin: Client, coll_id: str, sample: Path, wait_s: int) -> str:
    with sample.open("rb") as fh:
        r = admin.req("POST", "/documents/upload",
                      data={"collection_id": coll_id},
                      files={"file": (sample.name, fh)})
    r.raise_for_status()
    doc_id = r.json()["document"]["id"]
    deadline = time.time() + wait_s
    while time.time() < deadline:
        st = admin.req("GET", f"/documents/{doc_id}/ingest-status").json()
        if st and st.get("status") in ("indexed", "failed"):
            break
        time.sleep(3)
    return doc_id


def run(args: argparse.Namespace) -> int:
    admin = Client(args.base_url, args.timeout)
    admin.login(args.admin_email, args.admin_password)

    print(">> provisioning two isolated tenants")
    a = _provision(admin, "A")
    b = _provision(admin, "B")

    print(">> uploading + indexing a distinct document per collection")
    a_doc = _upload_and_index(admin, a["coll"]["id"], SAMPLES / "normal.pdf", args.wait_s)
    b_doc = _upload_and_index(admin, b["coll"]["id"], SAMPLES / "table.pdf", args.wait_s)

    # Attacker = user A. Victim data = collection B / document b_doc.
    attacker = Client(args.base_url, args.timeout)
    attacker.login(a["email"], a["password"])
    victim = Client(args.base_url, args.timeout)
    victim.login(b["email"], b["password"])

    res = Result()
    print(">> probing every retrieval path as user A against user B's data")

    # 1. text search
    r = attacker.req("POST", "/search", json={"query": "Tabelle Werte Zeile Spalte",
                                              "top_k": 10, "include_pages": True})
    body = r.json()
    text_ids = {c["document_id"] for c in body.get("results", [])}
    res.add("text_search", "collB doc absent from /search results",
            b_doc not in text_ids, f"{len(text_ids)} results")

    # 2. visual pages
    page_ids = {p["document_id"] for p in body.get("pages", [])}
    res.add("visual_pages", "collB doc absent from /search page hits",
            b_doc not in page_ids, f"{len(page_ids)} pages")

    # 4. media (MinIO) — page + figure objects of B's doc
    rp = attacker.req("GET", f"/media/pages/{b_doc}/1")
    res.add("media_page", "GET /media/pages/{Bdoc}/1 blocked",
            rp.status_code == 404, f"HTTP {rp.status_code}")
    rf = attacker.req("GET", f"/media/figures/{b_doc}/figure-0")
    res.add("media_figure", "GET /media/figures/{Bdoc}/… blocked",
            rf.status_code == 404, f"HTTP {rf.status_code}")

    # 6. direct object access
    rd = attacker.req("GET", f"/documents/{b_doc}")
    res.add("direct_document", "GET /documents/{Bdoc} blocked",
            rd.status_code == 404, f"HTTP {rd.status_code}")
    ri = attacker.req("GET", f"/documents/{b_doc}/ingest-status")
    res.add("ingest_status", "GET /documents/{Bdoc}/ingest-status blocked",
            ri.status_code == 404, f"HTTP {ri.status_code}")
    rl = attacker.req("GET", "/documents")
    listed = {d["id"] for d in rl.json()}
    res.add("document_list", "collB doc absent from A's /documents list",
            b_doc not in listed, f"{len(listed)} listed")

    if not args.skip_chat:
        # 3. semantic cache — victim populates cache under B's scope, attacker
        #    asks the SAME question and must NOT get a cross-scope hit.
        q = "Welche Werte stehen in der Tabelle?"
        victim.req("POST", "/chat", json={"message": q})
        ra = attacker.req("POST", "/chat", json={"message": q})
        turn = ra.json()
        cited = {c.get("document_id") for c in turn.get("citations", [])}
        res.add("semantic_cache", "A gets no cross-scope cache hit / no collB citation",
                (turn.get("cache_hit") is not True) and (b_doc not in cited),
                f"cache_hit={turn.get('cache_hit')} cited={len(cited)}")

        # 5. metadata lookup — "which documents exist" must not reveal B's file
        rm = attacker.req("POST", "/chat", json={"message": "Welche Dokumente gibt es?"})
        answer = (rm.json().get("answer") or "")
        res.add("metadata_lookup", "collB filename absent from A's metadata answer",
                "table.pdf" not in answer.lower(), f"answer={len(answer)} chars")

    # ---- report ----
    leaks = res.leaks
    lines = [
        "# ACL red-team report (Phase 5)",
        "",
        f"- Date: {time.strftime('%Y-%m-%d %H:%M')}  ·  Backend: `{args.base_url}`",
        f"- Tenants: A=`{a['coll']['name']}` (doc {a_doc}), "
        f"B=`{b['coll']['name']}` (doc {b_doc})",
        f"- Attacker: user A ({a['email']}) attempting to reach collection B",
        f"- Probes: {len(res.probes)}  ·  **Bypasses found: {len(leaks)}**",
        "",
        "| path | probe | result |",
        "|---|---|---|",
    ]
    for p in res.probes:
        lines.append(f"| {p.path} | {p.description} | "
                     f"{'✅ denied' if p.denied else '❌ LEAK'} ({p.detail}) |")
    lines += ["", ("**RESULT: zero ACL bypasses across all probed paths.**"
                   if not leaks else
                   f"**RESULT: {len(leaks)} BYPASS(ES) — CRITICAL, halt cutover.**"), ""]
    report = "\n".join(lines)

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nreport: {out}")
    print(report.split("| path", 1)[0])

    if leaks:
        print(f"FAILED: {len(leaks)} ACL bypass(es) found", file=sys.stderr)
        return 1
    print("PASSED: zero ACL bypasses")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--admin-email", default="admin@example.com")
    ap.add_argument("--admin-password", default="admin-pass-123")
    ap.add_argument("--report", default="eval/reports/phase5_redteam.md")
    ap.add_argument("--wait-s", type=int, default=180, help="max wait for indexing")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--skip-chat", action="store_true",
                    help="skip the two slow chat-based probes (cache, metadata)")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
