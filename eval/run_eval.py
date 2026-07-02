"""Golden-set eval runner (Phase 0) — batch scoring over a LIVE backend.

Runs every case in eval/golden_v2.jsonl against the HTTP API (auth → /search →
/chat), computes deterministic metrics plus an optional LLM-judge correctness
score, and writes a Markdown report + JSON results to eval/reports/.

Metrics per case
  retrieval  hit@1/3/5      target document appears in /search results
             page_hit@5     ... on one of the ground-truth pages
  answer     contains_pass  all expect_contains substrings in the answer
             insufficient   expect_insufficient matched by the system
             citation_pass  expect_citation matched (>=1 citation present)
             citation_ok    >=1 citation points at the ground-truth document
  judge      correctness    0..1, local LLM compares answer vs expected_answer
                            (same rubric style as app/eval/judge.py; --no-judge
                            to skip; judged via the OpenAI-compatible endpoint)

A case PASSES when: insufficient expectation matches; and (for answerable
cases) contains_pass and citation expectation hold.

Usage (dev stack):
  python eval/run_eval.py --base-url http://localhost:8000 \
      --email admin@example.com --password admin-pass-123 \
      --golden eval/golden_v2.jsonl --report baseline
Optional: --upload-dir eval/fixtures/corpus --collection <name-or-id> uploads
the corpus first and waits for indexing (idempotent — duplicates are skipped
by the backend's content-hash dedupe).

Standalone by design: stdlib + httpx only, no app.* imports, so it runs from
the host against any deployment (dev laptop or prod GPU server).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

INSUFFICIENT_MARKERS = (
    "insufficient evidence",
    "nicht genügend belege",
    "keine ausreichenden informationen",
)
# 429/503 are transient (quota, backend restart) — retry. 504 means the
# backend's own request-duration circuit breaker fired; that is a case result
# (timeout), not a transient error, so it is NOT retried.
RETRY_STATUS = {429, 502, 503}
MAX_RETRIES = 6


class CaseTimeout(Exception):
    """Backend 504 or client read timeout — scored as a failed case."""


# --------------------------------------------------------------------------
# Golden-set loading
# --------------------------------------------------------------------------

def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    return cases


def filter_subset(cases: list[dict[str, Any]], subset: str) -> list[dict[str, Any]]:
    if subset == "all":
        return cases
    if subset == "text":
        return [c for c in cases if c["modality"] == "text"]
    if subset == "visual":
        return [c for c in cases if c["modality"] != "text"]
    return [c for c in cases if c["modality"] == subset]


# --------------------------------------------------------------------------
# Deterministic scoring (unit-tested in eval/test_run_eval.py)
# --------------------------------------------------------------------------

def is_insufficient(answer: str, flag: bool) -> bool:
    low = (answer or "").strip().lower()
    return flag or not low or any(m in low for m in INSUFFICIENT_MARKERS)


def contains_pass(answer: str, expect_contains: list[str]) -> bool:
    low = (answer or "").lower()
    return all(s.lower() in low for s in expect_contains)


def hit_at_k(result_doc_ids: list[str], target_doc_ids: set[str], k: int) -> bool:
    return any(d in target_doc_ids for d in result_doc_ids[:k])


def page_hit_at_k(
    results: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    doc_by_file: dict[str, str],
    k: int,
) -> bool:
    """True if a top-k result lands on a ground-truth (document, page) pair.
    Targets without page info fall back to a document-level match."""
    for r in results[:k]:
        for t in targets:
            doc_id = doc_by_file.get(t["file"])
            if doc_id is None or str(r.get("document_id")) != doc_id:
                continue
            pages = t.get("pages") or []
            if not pages or r.get("page_number") in pages:
                return True
    return False


def citation_ok(citations: list[dict[str, Any]], target_doc_ids: set[str]) -> bool:
    return any(str(c.get("document_id")) in target_doc_ids for c in citations)


def case_passed(case: dict[str, Any], row: dict[str, Any]) -> bool:
    if case["expect_insufficient"]:
        return bool(row["insufficient"])
    if row["insufficient"]:
        return False
    if not row["contains_pass"]:
        return False
    if case["expect_citation"] and not row["citations_present"]:
        return False
    return True


# --------------------------------------------------------------------------
# HTTP client with 429/5xx backoff
# --------------------------------------------------------------------------

class Backend:
    def __init__(self, base_url: str, email: str, password: str, timeout: float) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=timeout)
        self.email, self.password = email, password
        self._login()

    def _login(self) -> None:
        r = self.http.post("/auth/login", json={"email": self.email, "password": self.password})
        r.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        for attempt in range(MAX_RETRIES):
            try:
                r = self.http.request(method, url, **kw)
            except httpx.TimeoutException as exc:
                raise CaseTimeout(f"client timeout on {url}") from exc
            if r.status_code == 401:          # access token expired mid-run
                self._login()
                continue
            if r.status_code == 504:
                raise CaseTimeout(f"backend 504 on {url}")
            if r.status_code in RETRY_STATUS:
                wait = min(2.0 * (attempt + 1), 15.0)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()
        return r

    # -- API wrappers ------------------------------------------------------
    def documents(self) -> list[dict[str, Any]]:
        return self.request("GET", "/documents").json()

    def collections(self) -> list[dict[str, Any]]:
        return self.request("GET", "/collections").json()

    def upload(self, collection_id: str, path: Path) -> dict[str, Any]:
        with path.open("rb") as fh:
            r = self.request(
                "POST", "/documents/upload",
                data={"collection_id": collection_id},
                files={"file": (path.name, fh)},
            )
        return r.json()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        r = self.request("POST", "/search", json={"query": query, "top_k": top_k, "top_n": top_k})
        return r.json()["results"]

    def chat(self, message: str) -> dict[str, Any]:
        return self.request("POST", "/chat", json={"message": message}).json()


# --------------------------------------------------------------------------
# LLM judge (local OpenAI-compatible endpoint; optional)
# --------------------------------------------------------------------------

class Judge:
    RUBRIC = (
        "You grade RAG answers. Compare the ANSWER against the REFERENCE for the "
        "QUESTION. Score factual agreement only; wording, language (German or "
        "English) and extra correct detail do not matter. "
        "Reply with a single integer 0-10."
    )

    def __init__(self, base_url: str, model: str, api_key: str, timeout: float) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=timeout,
                                 headers={"Authorization": f"Bearer {api_key}"})
        self.model = model

    def correctness(self, question: str, reference: str, answer: str) -> float:
        user = f"QUESTION: {question}\n\nREFERENCE: {reference}\n\nANSWER: {answer}"
        try:
            r = self.http.post("/chat/completions", json={
                "model": self.model, "temperature": 0.0, "max_tokens": 8,
                "messages": [{"role": "system", "content": self.RUBRIC},
                             {"role": "user", "content": user}],
            })
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            digits = "".join(ch for ch in text if ch.isdigit())
            return max(0.0, min(1.0, int(digits[:2] or "5") / 10.0)) if digits else 0.5
        except Exception:  # noqa: BLE001 - judge failure must not abort the run
            return 0.5


# --------------------------------------------------------------------------
# Corpus upload + indexing wait (optional, idempotent)
# --------------------------------------------------------------------------

def ensure_corpus(backend: Backend, upload_dir: Path, collection: str,
                  wait_s: int) -> None:
    colls = backend.collections()
    match = [c for c in colls if c["name"] == collection or str(c["id"]) == collection]
    if not match:
        sys.exit(f"collection {collection!r} not found (available: {[c['name'] for c in colls]})")
    cid = str(match[0]["id"])

    files = sorted(p for p in upload_dir.iterdir() if p.is_file())
    for path in files:
        res = backend.upload(cid, path)
        state = "duplicate" if res["duplicate"] else res["document"]["status"]
        print(f"  upload {path.name}: {state}")

    deadline = time.time() + wait_s
    while time.time() < deadline:
        docs = [d for d in backend.documents() if str(d["collection_id"]) == cid]
        pending = [d for d in docs if d["status"] not in ("INDEXED", "FAILED", "indexed", "failed")]
        failed = [d for d in docs if d["status"] in ("FAILED", "failed")]
        if not pending:
            for d in failed:
                print(f"  FAILED: {d['filename']}: {d.get('error')}")
            return
        print(f"  waiting for indexing: {len(pending)} pending ...")
        time.sleep(5)
    sys.exit("indexing did not finish within --wait-s")


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

@dataclass
class Aggregate:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def rate(self, key: str, subset: list[dict[str, Any]] | None = None) -> float:
        rows = self.rows if subset is None else subset
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return 0.0
        if isinstance(vals[0], bool):
            return sum(1 for v in vals if v) / len(vals)
        return statistics.mean(vals)

    def by(self, field_name: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in self.rows:
            out.setdefault(r[field_name], []).append(r)
        return out


def run(args: argparse.Namespace) -> int:
    golden = Path(args.golden)
    cases = filter_subset(load_cases(golden), args.subset)
    if args.limit:
        cases = cases[: args.limit]
    print(f"{len(cases)} cases ({args.subset}) from {golden}")

    backend = Backend(args.base_url, args.email, args.password, args.timeout)
    if args.upload_dir:
        ensure_corpus(backend, Path(args.upload_dir), args.collection, args.wait_s)

    doc_by_file = {d["filename"]: str(d["id"]) for d in backend.documents()}
    missing = {t["file"] for c in cases for t in c["retrieval_targets"]} - set(doc_by_file)
    if missing:
        sys.exit(f"golden targets not present in backend: {sorted(missing)} "
                 f"(run with --upload-dir eval/fixtures/corpus)")

    judge = None
    if not args.no_judge:
        judge = Judge(args.judge_url, args.judge_model, args.judge_api_key, args.timeout)

    agg = Aggregate()
    t_start = time.time()
    for i, case in enumerate(cases, 1):
        targets = case["retrieval_targets"]
        target_docs = {doc_by_file[t["file"]] for t in targets if t["file"] in doc_by_file}

        row: dict[str, Any] = {
            "id": case["id"], "lang": case["lang"], "modality": case["modality"],
            "hit@1": None, "hit@3": None, "hit@5": None, "page_hit@5": None,
            "error": None,
        }
        try:
            if targets:
                results = backend.search(case["query"], top_k=5)
                ids = [str(r["document_id"]) for r in results]
                row["hit@1"] = hit_at_k(ids, target_docs, 1)
                row["hit@3"] = hit_at_k(ids, target_docs, 3)
                row["hit@5"] = hit_at_k(ids, target_docs, 5)
                row["page_hit@5"] = page_hit_at_k(results, targets, doc_by_file, 5)

            turn = backend.chat(case["query"])
            answer = turn.get("answer", "")
            citations = turn.get("citations", [])
            row.update({
                "insufficient": is_insufficient(answer, turn.get("insufficient", False)),
                "contains_pass": contains_pass(answer, case["expect_contains"]),
                "citations_present": bool(citations),
                "citation_ok": citation_ok(citations, target_docs) if targets else None,
                "route": turn.get("route"), "cache_hit": turn.get("cache_hit", False),
                "answer": answer[:400],
            })
            row["passed"] = case_passed(case, row)
            if judge is not None and not case["expect_insufficient"]:
                row["judge_correctness"] = judge.correctness(
                    case["query"], case["expected_answer"], answer)
        except (CaseTimeout, httpx.HTTPStatusError) as exc:
            # A timed-out or errored turn is a FAILED case, not an aborted run.
            row.update({
                "insufficient": False, "contains_pass": False,
                "citations_present": False, "citation_ok": None,
                "route": None, "cache_hit": False,
                "answer": "", "passed": False, "error": str(exc),
            })
        agg.rows.append(row)
        mark = "PASS" if row["passed"] else "fail"
        err = f" error={row['error']}" if row["error"] else ""
        print(f"[{i:3}/{len(cases)}] {case['id']} {mark} "
              f"hit@5={row['hit@5']} route={row['route']}{err}", flush=True)

    elapsed = time.time() - t_start
    report_md = render_report(agg, args, elapsed, len(cases))
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{args.report}.md").write_text(report_md, encoding="utf-8")
    (reports_dir / f"{args.report}.json").write_text(
        json.dumps({"args": vars(args), "rows": agg.rows}, indent=2, default=str),
        encoding="utf-8")
    print(f"\nreport: {reports_dir / (args.report + '.md')}")
    print(report_md.split("## Per-case", 1)[0])
    return 0


def render_report(agg: Aggregate, args: argparse.Namespace, elapsed: float,
                  n: int) -> str:
    def pct(v: float) -> str:
        return f"{100 * v:.1f}%"

    lines = [
        f"# Eval report: {args.report}",
        "",
        f"- Date: {time.strftime('%Y-%m-%d %H:%M')}  ·  Cases: {n}  ·  "
        f"Subset: {args.subset}  ·  Duration: {elapsed / 60:.1f} min",
        f"- Backend: `{args.base_url}`  ·  Judge: "
        f"{'off' if args.no_judge else args.judge_model}",
        "",
        "## Aggregate",
        "",
        "| metric | overall |",
        "|---|---|",
        f"| pass rate | {pct(agg.rate('passed'))} |",
        f"| retrieval hit@1 | {pct(agg.rate('hit@1'))} |",
        f"| retrieval hit@3 | {pct(agg.rate('hit@3'))} |",
        f"| retrieval hit@5 | {pct(agg.rate('hit@5'))} |",
        f"| page hit@5 | {pct(agg.rate('page_hit@5'))} |",
        f"| citation present | {pct(agg.rate('citations_present'))} |",
        f"| citation → correct doc | {pct(agg.rate('citation_ok'))} |",
        f"| timeouts/errors | {sum(1 for r in agg.rows if r.get('error'))} |",
    ]
    if not args.no_judge:
        lines.append(f"| judge correctness | {pct(agg.rate('judge_correctness'))} |")
    lines += ["", "## By modality", "",
              "| modality | n | pass | hit@5 | judge |", "|---|---|---|---|---|"]
    for mod, rows in sorted(agg.by("modality").items()):
        sub = Aggregate(rows)
        judge_s = "—" if args.no_judge else pct(sub.rate("judge_correctness"))
        lines.append(f"| {mod} | {len(rows)} | {pct(sub.rate('passed'))} | "
                     f"{pct(sub.rate('hit@5'))} | {judge_s} |")
    lines += ["", "## By language", "",
              "| lang | n | pass | hit@5 |", "|---|---|---|---|"]
    for lang, rows in sorted(agg.by("lang").items()):
        sub = Aggregate(rows)
        lines.append(f"| {lang} | {len(rows)} | {pct(sub.rate('passed'))} | "
                     f"{pct(sub.rate('hit@5'))} |")
    lines += ["", "## Per-case results", "",
              "| id | modality | pass | hit@5 | page@5 | cites ok | route |",
              "|---|---|---|---|---|---|---|"]
    for r in agg.rows:
        def b(v: Any) -> str:
            return "—" if v is None else ("✓" if v else "✗")
        lines.append(f"| {r['id']} | {r['modality']} | {b(r['passed'])} | "
                     f"{b(r['hit@5'])} | {b(r['page_hit@5'])} | "
                     f"{b(r['citation_ok'])} | {r['route'] or '—'} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", default="admin@example.com")
    ap.add_argument("--password", default="admin-pass-123")
    ap.add_argument("--golden", default="eval/golden_v2.jsonl")
    ap.add_argument("--subset", default="all",
                    choices=["all", "text", "visual", "table", "chart", "diagram", "scanned"])
    ap.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    ap.add_argument("--report", default="run", help="report name (eval/reports/<name>.md)")
    ap.add_argument("--reports-dir", default="eval/reports")
    ap.add_argument("--upload-dir", default=None,
                    help="upload all files from this dir before running (idempotent)")
    ap.add_argument("--collection", default=None,
                    help="target collection name or id (required with --upload-dir)")
    ap.add_argument("--wait-s", type=int, default=1800, help="max wait for indexing")
    ap.add_argument("--timeout", type=float, default=660.0,
                    help="client timeout; keep above the backend's "
                         "MAX_REQUEST_DURATION_S so the server 504s first")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--judge-url", default="http://localhost:11434/v1",
                    help="OpenAI-compatible endpoint for the judge model")
    ap.add_argument("--judge-model", default="qwen2.5:3b")
    ap.add_argument("--judge-api-key", default="not-needed-local")
    args = ap.parse_args()
    if args.upload_dir and not args.collection:
        ap.error("--upload-dir requires --collection")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
