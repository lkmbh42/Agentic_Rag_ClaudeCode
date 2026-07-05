# ACL red-team report (Phase 5)

- Date: 2026-07-05 17:34  ·  Backend: `http://localhost:8000`
- Tenants: A=`redteam-A` (doc 4a51be3b-f29f-4ba5-8345-8db5d59a3957), B=`redteam-B` (doc 3b9fb9f7-646e-4e75-8e4a-20eff15d195a)
- Attacker: user A (redteam-A-bb0a94@example.com) attempting to reach collection B
- Probes: 9  ·  **Bypasses found: 0**

| path | probe | result |
|---|---|---|
| text_search | collB doc absent from /search results | ✅ denied (1 results) |
| visual_pages | collB doc absent from /search page hits | ✅ denied (0 pages) |
| media_page | GET /media/pages/{Bdoc}/1 blocked | ✅ denied (HTTP 404) |
| media_figure | GET /media/figures/{Bdoc}/… blocked | ✅ denied (HTTP 404) |
| direct_document | GET /documents/{Bdoc} blocked | ✅ denied (HTTP 404) |
| ingest_status | GET /documents/{Bdoc}/ingest-status blocked | ✅ denied (HTTP 404) |
| document_list | collB doc absent from A's /documents list | ✅ denied (1 listed) |
| semantic_cache | A gets no cross-scope cache hit / no collB citation | ✅ denied (cache_hit=False cited=1) |
| metadata_lookup | collB filename absent from A's metadata answer | ✅ denied (answer=75 chars) |

**RESULT: zero ACL bypasses across all probed paths.**
