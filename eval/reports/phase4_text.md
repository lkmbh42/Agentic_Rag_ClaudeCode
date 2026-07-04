# Eval report: phase4_text

- Date: 2026-07-04 12:11  ·  Cases: 100  ·  Subset: text  ·  Duration: 141.8 min
- Backend: `http://localhost:8000`  ·  Judge: qwen2.5:3b

## Aggregate

| metric | overall |
|---|---|
| pass rate | 68.0% |
| retrieval hit@1 | 64.1% |
| retrieval hit@3 | 73.9% |
| retrieval hit@5 | 75.0% |
| page hit@5 | 71.7% |
| visual (ColQwen2) hit@5 | 0.0% |
| citation present | 87.0% |
| citation → correct doc | 72.8% |
| timeouts/errors | 0 |
| judge correctness | 43.9% |

## By modality

| modality | n | pass | hit@5 | judge |
|---|---|---|---|---|
| text | 100 | 68.0% | 75.0% | 43.9% |

## By language

| lang | n | pass | hit@5 |
|---|---|---|---|
| de | 56 | 64.3% | 73.1% |
| en | 44 | 72.7% | 77.5% |

## Per-case results

| id | modality | pass | hit@5 | page@5 | cites ok | route |
|---|---|---|---|---|---|---|
| t001 | text | ✓ | ✓ | ✓ | ✓ | text |
| t002 | text | ✓ | ✓ | ✓ | ✓ | text |
| t003 | text | ✗ | ✓ | ✓ | ✗ | text |
| t004 | text | ✗ | ✓ | ✓ | ✗ | text |
| t005 | text | ✗ | ✗ | ✗ | ✗ | text |
| t006 | text | ✓ | ✓ | ✓ | ✓ | text |
| t007 | text | ✓ | ✓ | ✓ | ✓ | text |
| t008 | text | ✓ | ✓ | ✓ | ✓ | text |
| t009 | text | ✓ | ✓ | ✓ | ✓ | text |
| t010 | text | ✓ | ✓ | ✓ | ✓ | text |
| t011 | text | ✗ | ✗ | ✗ | ✗ | text |
| t012 | text | ✓ | ✓ | ✓ | ✓ | text |
| t013 | text | ✓ | ✓ | ✓ | ✓ | text |
| t014 | text | ✓ | ✓ | ✓ | ✓ | text |
| t015 | text | ✓ | ✓ | ✓ | ✓ | text |
| t016 | text | ✗ | ✗ | ✗ | ✗ | text |
| t017 | text | ✓ | ✓ | ✓ | ✓ | text |
| t018 | text | ✗ | ✓ | ✗ | ✗ | text |
| t019 | text | ✓ | ✗ | ✗ | ✓ | text |
| t020 | text | ✓ | ✓ | ✓ | ✓ | text |
| t021 | text | ✓ | ✗ | ✗ | ✓ | text |
| t022 | text | ✗ | ✗ | ✗ | ✗ | text |
| t023 | text | ✓ | ✓ | ✓ | ✓ | text |
| t024 | text | ✗ | ✗ | ✗ | ✗ | text |
| t025 | text | ✓ | ✓ | ✓ | ✓ | text |
| t026 | text | ✓ | ✓ | ✓ | ✓ | text |
| t027 | text | ✓ | ✓ | ✓ | ✓ | text |
| t028 | text | ✗ | ✓ | ✓ | ✓ | text |
| t029 | text | ✓ | ✓ | ✓ | ✓ | text |
| t030 | text | ✓ | ✓ | ✓ | ✓ | text |
| t031 | text | ✓ | ✓ | ✓ | ✓ | text |
| t032 | text | ✓ | ✗ | ✗ | ✗ | text |
| t033 | text | ✓ | ✓ | ✓ | ✓ | text |
| t034 | text | ✓ | ✓ | ✓ | ✓ | text |
| t035 | text | ✓ | ✓ | ✓ | ✓ | text |
| t036 | text | ✓ | ✓ | ✓ | ✓ | text |
| t037 | text | ✗ | ✗ | ✗ | ✗ | text |
| t038 | text | ✓ | ✓ | ✓ | ✓ | text |
| t039 | text | ✓ | ✓ | ✓ | ✓ | text |
| t040 | text | ✓ | ✓ | ✓ | ✓ | text |
| t041 | text | ✓ | ✓ | ✓ | ✓ | text |
| t042 | text | ✗ | ✗ | ✗ | ✗ | text |
| t043 | text | ✓ | ✓ | ✓ | ✓ | text |
| t044 | text | ✓ | ✓ | ✓ | ✓ | text |
| t045 | text | ✓ | ✓ | ✓ | ✓ | text |
| t046 | text | ✓ | ✓ | ✓ | ✓ | text |
| t047 | text | ✗ | ✗ | ✗ | ✗ | text |
| t048 | text | ✓ | ✓ | ✓ | ✓ | text |
| t049 | text | ✓ | ✓ | ✓ | ✓ | text |
| t050 | text | ✓ | ✓ | ✓ | ✓ | text |
| t051 | text | ✓ | ✓ | ✓ | ✓ | text |
| t052 | text | ✓ | ✓ | ✓ | ✓ | text |
| t053 | text | ✓ | ✓ | ✓ | ✓ | text |
| t054 | text | ✓ | ✓ | ✓ | ✓ | text |
| t055 | text | ✓ | ✓ | ✓ | ✓ | text |
| t056 | text | ✗ | ✗ | ✗ | ✗ | text |
| t057 | text | ✓ | ✓ | ✓ | ✓ | text |
| t058 | text | ✗ | ✗ | ✗ | ✗ | text |
| t059 | text | ✓ | ✓ | ✓ | ✓ | text |
| t060 | text | ✓ | ✓ | ✓ | ✓ | text |
| t061 | text | ✓ | ✓ | ✓ | ✓ | text |
| t062 | text | ✓ | ✓ | ✓ | ✓ | text |
| t063 | text | ✗ | ✓ | ✗ | ✗ | text |
| t064 | text | ✓ | ✓ | ✓ | ✓ | text |
| t065 | text | ✓ | ✓ | ✓ | ✓ | text |
| t066 | text | ✓ | ✓ | ✓ | ✓ | text |
| t067 | text | ✗ | ✗ | ✗ | ✗ | text |
| t068 | text | ✓ | ✓ | ✓ | ✓ | text |
| t069 | text | ✓ | ✓ | ✓ | ✓ | text |
| t070 | text | ✓ | ✓ | ✓ | ✓ | text |
| t071 | text | ✓ | ✓ | ✓ | ✓ | text |
| t072 | text | ✓ | ✓ | ✓ | ✓ | text |
| t073 | text | ✓ | ✓ | ✓ | ✓ | text |
| t074 | text | ✓ | ✓ | ✓ | ✓ | text |
| t075 | text | ✓ | ✓ | ✓ | ✓ | text |
| t076 | text | ✗ | ✗ | ✗ | ✗ | text |
| t077 | text | ✗ | ✗ | ✗ | ✗ | text |
| t078 | text | ✗ | ✓ | ✗ | ✗ | text |
| t079 | text | ✓ | ✓ | ✓ | ✓ | text |
| t080 | text | ✓ | ✓ | ✓ | ✓ | text |
| t081 | text | ✓ | ✓ | ✓ | ✓ | text |
| t082 | text | ✗ | ✗ | ✗ | ✗ | text |
| t083 | text | ✓ | ✓ | ✓ | ✓ | text |
| t084 | text | ✓ | ✓ | ✓ | ✓ | text |
| t085 | text | ✗ | ✗ | ✗ | ✗ | text |
| t086 | text | ✗ | ✗ | ✗ | ✓ | text |
| t087 | text | ✓ | ✓ | ✓ | ✓ | text |
| t088 | text | ✗ | ✗ | ✗ | ✗ | text |
| t089 | text | ✓ | ✗ | ✗ | ✗ | text |
| t090 | text | ✓ | ✗ | ✗ | ✗ | text |
| t091 | text | ✓ | ✓ | ✓ | ✓ | text |
| t092 | text | ✗ | ✗ | ✗ | ✗ | text |
| t093 | text | ✗ | — | — | — | text |
| t094 | text | ✗ | — | — | — | text |
| t095 | text | ✗ | — | — | — | text |
| t096 | text | ✗ | — | — | — | text |
| t097 | text | ✗ | — | — | — | text |
| t098 | text | ✗ | — | — | — | metadata |
| t099 | text | ✗ | — | — | — | text |
| t100 | text | ✗ | — | — | — | text |
