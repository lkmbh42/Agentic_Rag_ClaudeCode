# Eval report: baseline

- Date: 2026-07-02 18:09  ·  Cases: 130  ·  Subset: all  ·  Duration: 133.3 min
- Backend: `http://localhost:8000`  ·  Judge: qwen2.5:3b

## Aggregate

| metric | overall |
|---|---|
| pass rate | 61.5% |
| retrieval hit@1 | 52.9% |
| retrieval hit@3 | 62.0% |
| retrieval hit@5 | 65.3% |
| page hit@5 | 62.8% |
| citation present | 98.5% |
| citation → correct doc | 66.9% |
| timeouts/errors | 0 |
| judge correctness | 34.0% |

## By modality

| modality | n | pass | hit@5 | judge |
|---|---|---|---|---|
| chart | 11 | 9.1% | 50.0% | 0.0% |
| diagram | 4 | 0.0% | 25.0% | 0.0% |
| scanned | 3 | 100.0% | 66.7% | 33.3% |
| table | 12 | 50.0% | 25.0% | 11.7% |
| text | 100 | 70.0% | 73.9% | 42.1% |

## By language

| lang | n | pass | hit@5 |
|---|---|---|---|
| de | 80 | 57.5% | 65.3% |
| en | 50 | 68.0% | 65.2% |

## Per-case results

| id | modality | pass | hit@5 | page@5 | cites ok | route |
|---|---|---|---|---|---|---|
| t001 | text | ✓ | ✓ | ✓ | ✓ | — |
| t002 | text | ✓ | ✓ | ✓ | ✓ | — |
| t003 | text | ✗ | ✓ | ✓ | ✓ | — |
| t004 | text | ✓ | ✓ | ✓ | ✓ | — |
| t005 | text | ✗ | ✗ | ✗ | ✗ | — |
| t006 | text | ✓ | ✓ | ✓ | ✓ | — |
| t007 | text | ✓ | ✓ | ✓ | ✓ | — |
| t008 | text | ✓ | ✓ | ✓ | ✓ | — |
| t009 | text | ✓ | ✓ | ✓ | ✓ | — |
| t010 | text | ✓ | ✓ | ✓ | ✓ | — |
| t011 | text | ✓ | ✗ | ✗ | ✗ | — |
| t012 | text | ✓ | ✓ | ✓ | ✓ | — |
| t013 | text | ✓ | ✓ | ✓ | ✓ | — |
| t014 | text | ✓ | ✓ | ✓ | ✓ | — |
| t015 | text | ✓ | ✓ | ✓ | ✓ | — |
| t016 | text | ✓ | ✗ | ✗ | ✗ | — |
| t017 | text | ✓ | ✓ | ✓ | ✓ | — |
| t018 | text | ✗ | ✓ | ✗ | ✓ | — |
| t019 | text | ✓ | ✗ | ✗ | ✓ | — |
| t020 | text | ✓ | ✓ | ✓ | ✓ | — |
| t021 | text | ✗ | ✗ | ✗ | ✗ | — |
| t022 | text | ✗ | ✗ | ✗ | ✗ | — |
| t023 | text | ✓ | ✓ | ✓ | ✓ | — |
| t024 | text | ✗ | ✗ | ✗ | ✗ | — |
| t025 | text | ✓ | ✓ | ✓ | ✓ | — |
| t026 | text | ✓ | ✓ | ✓ | ✓ | — |
| t027 | text | ✓ | ✓ | ✓ | ✓ | — |
| t028 | text | ✓ | ✓ | ✓ | ✓ | — |
| t029 | text | ✓ | ✓ | ✓ | ✓ | — |
| t030 | text | ✓ | ✓ | ✓ | ✓ | — |
| t031 | text | ✓ | ✓ | ✓ | ✓ | — |
| t032 | text | ✓ | ✗ | ✗ | ✗ | — |
| t033 | text | ✓ | ✓ | ✓ | ✓ | — |
| t034 | text | ✓ | ✓ | ✓ | ✓ | — |
| t035 | text | ✓ | ✓ | ✓ | ✓ | — |
| t036 | text | ✓ | ✓ | ✓ | ✓ | — |
| t037 | text | ✗ | ✗ | ✗ | ✗ | — |
| t038 | text | ✓ | ✓ | ✓ | ✓ | — |
| t039 | text | ✓ | ✓ | ✓ | ✓ | — |
| t040 | text | ✓ | ✓ | ✓ | ✓ | — |
| t041 | text | ✓ | ✓ | ✓ | ✓ | — |
| t042 | text | ✗ | ✗ | ✗ | ✗ | — |
| t043 | text | ✓ | ✓ | ✓ | ✓ | — |
| t044 | text | ✓ | ✓ | ✓ | ✓ | — |
| t045 | text | ✓ | ✓ | ✓ | ✓ | — |
| t046 | text | ✓ | ✓ | ✓ | ✓ | — |
| t047 | text | ✗ | ✗ | ✗ | ✗ | — |
| t048 | text | ✓ | ✓ | ✓ | ✓ | — |
| t049 | text | ✓ | ✓ | ✓ | ✓ | — |
| t050 | text | ✓ | ✓ | ✓ | ✓ | — |
| t051 | text | ✓ | ✓ | ✓ | ✓ | — |
| t052 | text | ✓ | ✓ | ✓ | ✓ | — |
| t053 | text | ✓ | ✓ | ✓ | ✓ | — |
| t054 | text | ✓ | ✓ | ✓ | ✓ | — |
| t055 | text | ✓ | ✓ | ✓ | ✓ | — |
| t056 | text | ✗ | ✗ | ✗ | ✗ | — |
| t057 | text | ✓ | ✓ | ✓ | ✓ | — |
| t058 | text | ✗ | ✗ | ✗ | ✗ | — |
| t059 | text | ✓ | ✓ | ✓ | ✓ | — |
| t060 | text | ✓ | ✓ | ✓ | ✓ | — |
| t061 | text | ✓ | ✓ | ✓ | ✓ | — |
| t062 | text | ✓ | ✓ | ✓ | ✓ | — |
| t063 | text | ✗ | ✓ | ✗ | ✓ | — |
| t064 | text | ✓ | ✓ | ✓ | ✓ | — |
| t065 | text | ✓ | ✓ | ✓ | ✓ | — |
| t066 | text | ✓ | ✓ | ✓ | ✓ | — |
| t067 | text | ✗ | ✗ | ✗ | ✗ | — |
| t068 | text | ✓ | ✓ | ✓ | ✓ | — |
| t069 | text | ✓ | ✓ | ✓ | ✓ | — |
| t070 | text | ✓ | ✓ | ✓ | ✓ | — |
| t071 | text | ✓ | ✓ | ✓ | ✓ | — |
| t072 | text | ✓ | ✓ | ✓ | ✓ | — |
| t073 | text | ✓ | ✓ | ✓ | ✓ | — |
| t074 | text | ✓ | ✓ | ✓ | ✓ | — |
| t075 | text | ✓ | ✓ | ✓ | ✓ | — |
| t076 | text | ✗ | ✗ | ✗ | ✗ | — |
| t077 | text | ✗ | ✗ | ✗ | ✗ | — |
| t078 | text | ✗ | ✗ | ✗ | ✓ | — |
| t079 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t080 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t081 | text | ✓ | ✓ | ✓ | ✓ | — |
| t082 | text | ✗ | ✗ | ✗ | ✗ | diagram_question |
| t083 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t084 | text | ✓ | ✓ | ✓ | ✓ | summarization |
| t085 | text | ✗ | ✗ | ✗ | ✗ | unsupported |
| t086 | text | ✗ | ✗ | ✗ | ✓ | unsupported |
| t087 | text | ✓ | ✓ | ✓ | ✓ | unsupported |
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
| v001 | chart | ✗ | ✓ | ✓ | ✓ | summarization |
| v002 | chart | ✗ | ✓ | ✓ | ✓ | chart_question |
| v003 | chart | ✗ | ✗ | ✗ | ✗ | chart_question |
| v004 | chart | ✓ | ✗ | ✗ | ✗ | chart_question |
| v005 | chart | ✗ | ✗ | ✗ | ✗ | table_question |
| v006 | chart | ✗ | ✓ | ✓ | ✗ | complex_multi_step |
| v007 | chart | ✗ | ✗ | ✗ | ✗ | — |
| v008 | chart | ✗ | ✓ | ✓ | ✗ | chart_question |
| v009 | chart | ✗ | ✓ | ✗ | ✗ | chart_question |
| v010 | chart | ✗ | ✗ | ✗ | ✗ | table_question |
| v011 | table | ✓ | ✗ | ✗ | ✗ | table_question |
| v012 | table | ✗ | ✓ | ✓ | ✓ | table_question |
| v013 | table | ✓ | ✗ | ✗ | ✗ | summarization |
| v014 | table | ✓ | ✗ | ✗ | ✓ | summarization |
| v015 | table | ✓ | ✓ | ✓ | ✗ | chart_question |
| v016 | table | ✓ | ✓ | ✓ | ✓ | summarization |
| v017 | table | ✗ | ✗ | ✗ | ✗ | table_question |
| v018 | table | ✓ | ✗ | ✗ | ✗ | table_question |
| v019 | table | ✗ | ✗ | ✗ | ✗ | table_question |
| v020 | table | ✗ | ✗ | ✗ | ✗ | summarization |
| v021 | table | ✗ | ✗ | ✗ | ✗ | chart_question |
| v022 | table | ✗ | ✗ | ✗ | ✗ | chart_question |
| v023 | diagram | ✗ | ✗ | ✗ | ✗ | diagram_question |
| v024 | diagram | ✗ | ✓ | ✓ | ✓ | diagram_question |
| v025 | diagram | ✗ | ✗ | ✗ | ✓ | diagram_question |
| v026 | diagram | ✗ | ✗ | ✗ | ✗ | diagram_question |
| v027 | scanned | ✓ | ✗ | ✗ | ✓ | chart_question |
| v028 | scanned | ✓ | ✓ | ✓ | ✓ | diagram_question |
| v029 | scanned | ✓ | ✓ | ✓ | ✓ | diagram_question |
| v030 | chart | ✗ | — | — | — | unsupported |

## Provenance

- Git commit at eval time: `1d589ea` (`fix(phase0): audit finding remediations`, branch `feat/multimodal-migration`)
- Stack: dev compose (`docker-compose.dev.yml`, project `agentic-rag-dev`), all services healthy at run start; 0 timeouts/errors over the 133-minute run
- Answer LLM: `qwen2.5:3b` via local Ollama (`http://ollama:11434/v1`), Ollama model ID `357c53fb659c` (locally staged per `scripts/stage-dev-models.sh` — no runtime downloads)
- Judge LLM: same local model/endpoint (`http://localhost:11434/v1`, `qwen2.5:3b`) — no external endpoint involved anywhere in the run
- Embeddings/reranker: dev-mode service (stub freeze per `docs/PINS.md` §1); prod BGE-M3/bge-reranker arrive with Phase 1 provisioning
- HF revision pins: none exist yet by design — see `docs/PINS.md` §4 (operator fills `<HF_REVISION_HASH>` during Phase 1 provisioning)
- Corpus: 9 synthetic DE/EN fixture documents (`eval/fixtures/corpus/`, committed in `30bc1ea`), all `indexed` before the run
- Interpretation: visual subsets (chart 0.0%, diagram 0.0%, table 11.7%, scanned 33.3% judge correctness) fail as expected — this IS the baseline the multimodal migration is measured against. Do not tune against this report.
- Raw per-case rows (incl. answers): `eval/reports/baseline.json`
