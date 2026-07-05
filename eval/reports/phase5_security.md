# Phase 5 security pass — dependency audit + hardening

- Date: 2026-07-05 · Backend: `pip-audit -r requirements.txt` · Frontend: `npm audit --omit=dev`

## Frontend (admin-ui)

`npm audit --omit=dev` → **0 vulnerabilities** (lockfileVersion 3, React 18 + Vite).

## Backend (pip-audit)

**26 known vulnerabilities across 6 packages.** None are silently bumped: the
langgraph and starlette fixes are major-version jumps that would destabilize the
gated, working system on the eve of cutover, so they are recorded with triage and
a remediation plan for operator ratification (a dedicated patch cycle after the
pilot, re-gated through the eval suite), not applied blind.

| Package | Cur | Fix | Findings | Exploitability in THIS deployment | Decision |
|---|---|---|---|---|---|
| pillow | 11.3.0 | 12.2.0 | 6 (image-parsing: PYSEC-2026-165, CVE-2026-25990/40192/42309/42310/42311) | Ingestion parses images from the **internal, authenticated** corpus + page renders — no anonymous upload path. Moderate: malformed image in an ingested doc. | **Patch candidate now** — pillow is the most contained bump; verify against the docling/pymupdf image pipeline, re-run the `docling` test suite. Flagged for operator go-ahead. |
| starlette | 0.46.2 | ≥1.1.0 | 8 (multipart/request-parsing DoS + CVE-2025-54121/62727, CVE-2026-48817/48818) | Behind JWT auth (authenticated employees only) and the reverse proxy; upload size cap is an AUDIT §11 deferred item. Transitively pinned by FastAPI — cannot bump in isolation. | **Coordinated FastAPI+starlette bump in a patch cycle**, full re-test. Interim: enforce the deferred upload size cap + proxy body limits. |
| langgraph | 0.2.76 | 1.0.10 | 2 (PYSEC-2026-83) | Graph orchestration; 0.2→1.0 is a breaking major. | **Post-cutover major upgrade**, re-gate the whole graph test suite. |
| langgraph-checkpoint | 2.1.2 | ≥4.1.1 | 3 (CVE-2025-64439, CVE-2026-27794/48775 — checkpoint deserialization) | The checkpointer (de)serializes **graph state we produce**, persisted to our own Postgres — not attacker-controlled input. Low. | Bundled with the langgraph major upgrade. |
| langgraph-sdk | 0.1.74 | 0.3.15 | 1 (CVE-2026-48776) | SDK client surface; not on the request path. Low. | Bundled with the langgraph upgrade. |

### Air-gap context (why these are lower-severity here, not why they're ignored)

Rule 2 means no runtime external calls; the only network ingress is the
JWT-authenticated API behind the reverse proxy, used by ~500 internal employees.
There is no anonymous or internet-facing attack surface. Every finding above is
reachable only by an authenticated employee, which bounds — but does not
eliminate — exploitability. The remediation plan above still schedules every fix.

## Container hardening (applied this phase)

- Every prod service already runs as a **non-root uid** (`docker/*.Dockerfile`,
  uid 10001–10004).
- **`no-new-privileges:true`** now set on all 13 prod services (compose
  `x-hardening` anchor) — blocks setuid escalation.
- MinIO is **internal-network-only**; object bytes are served exclusively through
  the ACL-checked gateway `/media` endpoints (never presigned/public).
- Secrets are `.env`-only; SSE-S3 encrypts every object at rest.

## Remediation plan (operator ratifies at the gate)

1. **Now (low-risk):** attempt the pillow 11.3→12.2 bump; re-run `docling` +
   `figures`/`pages` tests; keep if green.
2. **Interim mitigation:** enforce the deferred upload size cap (AUDIT §11) +
   proxy `client_max_body_size` to blunt the starlette multipart DoS vectors.
3. **Patch cycle (post-pilot):** coordinated FastAPI+starlette bump and the
   langgraph 1.x major upgrade, each re-gated through the full test + eval suite.
