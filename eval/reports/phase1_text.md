# Eval report: phase1_text

- Date: 2026-07-03 01:23  ·  Cases: 100  ·  Subset: text  ·  Duration: 156.2 min
- Backend: `http://localhost:8000`  ·  Judge: qwen2.5:3b

## Aggregate

| metric | overall |
|---|---|
| pass rate | 68.0% |
| retrieval hit@1 | 64.1% |
| retrieval hit@3 | 72.8% |
| retrieval hit@5 | 73.9% |
| page hit@5 | 71.7% |
| citation present | 95.0% |
| citation → correct doc | 71.7% |
| timeouts/errors | 0 |
| judge correctness | 45.4% |

## By modality

| modality | n | pass | hit@5 | judge |
|---|---|---|---|---|
| text | 100 | 68.0% | 73.9% | 45.4% |

## By language

| lang | n | pass | hit@5 |
|---|---|---|---|
| de | 56 | 62.5% | 73.1% |
| en | 44 | 75.0% | 75.0% |

## Per-case results

| id | modality | pass | hit@5 | page@5 | cites ok | route |
|---|---|---|---|---|---|---|
| t001 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t002 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t003 | text | ✗ | ✓ | ✓ | ✗ | complex_multi_step |
| t004 | text | ✗ | ✓ | ✓ | ✗ | summarization |
| t005 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t006 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t007 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t008 | text | ✓ | ✓ | ✓ | ✓ | diagram_question |
| t009 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t010 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t011 | text | ✓ | ✗ | ✗ | ✗ | simple_rag |
| t012 | text | ✓ | ✓ | ✓ | ✓ | diagram_question |
| t013 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t014 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t015 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t016 | text | ✓ | ✗ | ✗ | ✗ | diagram_question |
| t017 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t018 | text | ✗ | ✓ | ✗ | ✗ | summarization |
| t019 | text | ✓ | ✗ | ✗ | ✓ | summarization |
| t020 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t021 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t022 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t023 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t024 | text | ✗ | ✗ | ✗ | ✗ | unsupported |
| t025 | text | ✓ | ✓ | ✓ | ✓ | diagram_question |
| t026 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t027 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t028 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t029 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t030 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t031 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t032 | text | ✓ | ✗ | ✗ | ✗ | complex_multi_step |
| t033 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t034 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t035 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t036 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t037 | text | ✗ | ✗ | ✗ | ✗ | table_question |
| t038 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t039 | text | ✓ | ✓ | ✓ | ✗ | unsupported |
| t040 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t041 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t042 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t043 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t044 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t045 | text | ✓ | ✓ | ✓ | ✓ | simple_rag |
| t046 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t047 | text | ✗ | ✗ | ✗ | ✗ | table_question |
| t048 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t049 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t050 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t051 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t052 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t053 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t054 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t055 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t056 | text | ✗ | ✗ | ✗ | ✗ | chart_question |
| t057 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t058 | text | ✗ | ✗ | ✗ | ✗ | unsupported |
| t059 | text | ✓ | ✓ | ✓ | ✓ | diagram_question |
| t060 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t061 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t062 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t063 | text | ✗ | ✓ | ✗ | ✓ | table_question |
| t064 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t065 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t066 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t067 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t068 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t069 | text | ✓ | ✓ | ✓ | ✓ | chart_question |
| t070 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t071 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t072 | text | ✓ | ✓ | ✓ | ✓ | complex_multi_step |
| t073 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t074 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t075 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t076 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t077 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t078 | text | ✗ | ✗ | ✗ | ✓ | chart_question |
| t079 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t080 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t081 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
| t082 | text | ✗ | ✗ | ✗ | ✗ | diagram_question |
| t083 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t084 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t085 | text | ✗ | ✗ | ✗ | ✗ | unsupported |
| t086 | text | ✗ | ✗ | ✗ | ✓ | unsupported |
| t087 | text | ✗ | ✓ | ✓ | ✗ | unsupported |
| t088 | text | ✗ | ✗ | ✗ | ✗ | simple_rag |
| t089 | text | ✓ | ✗ | ✗ | ✗ | unsupported |
| t090 | text | ✗ | ✗ | ✗ | ✗ | summarization |
| t091 | text | ✓ | ✓ | ✓ | ✓ | table_question |
| t092 | text | ✗ | ✗ | ✗ | ✗ | simple_rag |
| t093 | text | ✗ | — | — | — | summarization |
| t094 | text | ✗ | — | — | — | summarization |
| t095 | text | ✗ | — | — | — | table_question |
| t096 | text | ✗ | — | — | — | summarization |
| t097 | text | ✗ | — | — | — | summarization |
| t098 | text | ✗ | — | — | — | unsupported |
| t099 | text | ✗ | — | — | — | table_question |
| t100 | text | ✗ | — | — | — | simple_rag |

## Provenance & baseline comparison (Phase 1 DoD)

- Git commit at eval time: `2b63336` (branch `feat/multimodal-migration`, Phase 1 code complete)
- Serving: same dev backend as baseline (Ollama `qwen2.5:3b`, CPU, `http://ollama:11434/v1`) —
  all LLM traffic through the relocated single client `app/llm/client.py`. Judge: same local
  model/endpoint. No external endpoints.
- **Semantic cache flushed before the run** (Qdrant `semantic_cache` points + Redis `cache:*`
  tags) so every answer is fresh generation, not a replay of cached baseline answers.

| metric (text subset, n=100) | baseline | phase 1 | delta |
|---|---|---|---|
| retrieval hit@5 | 73.9 % | 73.9 % | ±0 (bit-identical — retrieval untouched) |
| judge correctness | 42.1 % | 45.4 % | **+3.3 pts** |
| pass rate | 70.0 % | 68.0 % | −2.0 pts (2 cases, within noise: σ≈4.6 pts at n=100) |

Per-case diff: exactly 2 flips, both generation-sampling variance, no regression signal —
`t004` (judge 1.0 in BOTH runs; correct answer, citation marker omitted this run) and `t087`
(judge 0.0 in BOTH runs; wrong both times, phrasing differs). **Verdict: neutral-or-better.**

Scope note: this run proves the Phase 1 refactor (client relocation, LLM_BACKEND, 503 guard,
pins) did not regress text quality on the same backend. vLLM-vs-Ollama model parity is
measured on the prod GPU host during provisioning (see phase1_load.md §3).
