# Phase 3 router report — intent classification on the labeled set

- Date: 2026-07-04 · Cases: 72 (eval/router_labeled.jsonl, DE+EN, 4 intents)
- Backend: `ollama` (dev CPU) · Model: `qwen2.5:3b` (classification role)
- Harness: `eval/router_report.py` (run inside the backend container); the same
  numbers are CI-gated by `tests/test_router.py::test_router_accuracy_on_labeled_set`
  (marker `llm`).

## Results

| metric | value | DoD target |
|---|---|---|
| accuracy | **94.4%** (68/72) | ≥90% ✅ |
| recall: text | 100% (20/20) | — |
| recall: metadata | 100% (16/16) | — |
| recall: visual | 88.9% (16/18) | — |
| recall: multi_doc | 88.9% (16/18) | — |
| latency p50 | 2617 ms | — (dev CPU) |
| latency p95 | 3481 ms | ≤400 ms **on vLLM** — ⚠️ GPU-host measurement |

## Misses (all degrade to `text` — the safe fallback path)

| id | expected | got | query gist |
|---|---|---|---|
| r034 | visual | text | "Read the values from the axis labels…" |
| r038 | visual | text | "Welche Symbole werden im Schaltplan verwendet?" |
| r059 | multi_doc | text | "Welche gemeinsamen Anforderungen nennen die IT-Richtlinie und die Datenschutzrichtlinie?" |
| r067 | multi_doc | text | "Which requirements appear in both the IT policy and the data protection policy?" |

Every misclassification lands on `text`, which still answers from the documents
via hybrid retrieval — no dead ends, no wrong-path hard failures. The two
multi_doc misses are two-document intersection questions that the text path
handles acceptably (both documents retrievable by one query).

## Latency note (flagged, same shape as Phase 1)

The 400 ms p95 DoD line applies to the prod serving stack (vLLM, Qwen2.5-3B on
GPU). The dev CPU Ollama measurement above is 9× that budget for the same
prompt (~350-token few-shot prefill + ≤16-token JSON completion) — a workload
vLLM serves in tens of milliseconds. `eval/router_report.py` re-runs the gate
at GPU provisioning; `tests/test_router.py` asserts the 400 ms line
automatically once `LLM_BACKEND=vllm`.
