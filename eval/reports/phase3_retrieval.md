# Eval report: phase3_retrieval

- Date: 2026-07-04 09:04  ·  Cases: 130  ·  Subset: all  ·  Duration: 0.1 min
- Backend: `http://localhost:8000`  ·  Judge: off

> **Retrieval-only run:** answer metrics (pass rate, citations, judge)
> were NOT measured — only the hit@k rows are meaningful.

## Aggregate

| metric | overall |
|---|---|
| pass rate | 0.0% |
| retrieval hit@1 | 52.9% |
| retrieval hit@3 | 61.2% |
| retrieval hit@5 | 65.3% |
| page hit@5 | 62.8% |
| visual (ColQwen2) hit@5 | 0.0% |
| citation present | 0.0% |
| citation → correct doc | 0.0% |
| timeouts/errors | 0 |

## By modality

| modality | n | pass | hit@5 | judge |
|---|---|---|---|---|
| chart | 11 | 0.0% | 50.0% | — |
| diagram | 4 | 0.0% | 25.0% | — |
| scanned | 3 | 0.0% | 66.7% | — |
| table | 12 | 0.0% | 25.0% | — |
| text | 100 | 0.0% | 73.9% | — |

## By language

| lang | n | pass | hit@5 |
|---|---|---|---|
| de | 80 | 0.0% | 65.3% |
| en | 50 | 0.0% | 65.2% |

## Per-case results

| id | modality | pass | hit@5 | page@5 | cites ok | route |
|---|---|---|---|---|---|---|
| t001 | text | — | ✓ | ✓ | — | — |
| t002 | text | — | ✓ | ✓ | — | — |
| t003 | text | — | ✓ | ✓ | — | — |
| t004 | text | — | ✓ | ✓ | — | — |
| t005 | text | — | ✗ | ✗ | — | — |
| t006 | text | — | ✓ | ✓ | — | — |
| t007 | text | — | ✓ | ✓ | — | — |
| t008 | text | — | ✓ | ✓ | — | — |
| t009 | text | — | ✓ | ✓ | — | — |
| t010 | text | — | ✓ | ✓ | — | — |
| t011 | text | — | ✗ | ✗ | — | — |
| t012 | text | — | ✓ | ✓ | — | — |
| t013 | text | — | ✓ | ✓ | — | — |
| t014 | text | — | ✓ | ✓ | — | — |
| t015 | text | — | ✓ | ✓ | — | — |
| t016 | text | — | ✗ | ✗ | — | — |
| t017 | text | — | ✓ | ✓ | — | — |
| t018 | text | — | ✓ | ✗ | — | — |
| t019 | text | — | ✗ | ✗ | — | — |
| t020 | text | — | ✓ | ✓ | — | — |
| t021 | text | — | ✗ | ✗ | — | — |
| t022 | text | — | ✗ | ✗ | — | — |
| t023 | text | — | ✓ | ✓ | — | — |
| t024 | text | — | ✗ | ✗ | — | — |
| t025 | text | — | ✓ | ✓ | — | — |
| t026 | text | — | ✓ | ✓ | — | — |
| t027 | text | — | ✓ | ✓ | — | — |
| t028 | text | — | ✓ | ✓ | — | — |
| t029 | text | — | ✓ | ✓ | — | — |
| t030 | text | — | ✓ | ✓ | — | — |
| t031 | text | — | ✓ | ✓ | — | — |
| t032 | text | — | ✗ | ✗ | — | — |
| t033 | text | — | ✓ | ✓ | — | — |
| t034 | text | — | ✓ | ✓ | — | — |
| t035 | text | — | ✓ | ✓ | — | — |
| t036 | text | — | ✓ | ✓ | — | — |
| t037 | text | — | ✗ | ✗ | — | — |
| t038 | text | — | ✓ | ✓ | — | — |
| t039 | text | — | ✓ | ✓ | — | — |
| t040 | text | — | ✓ | ✓ | — | — |
| t041 | text | — | ✓ | ✓ | — | — |
| t042 | text | — | ✗ | ✗ | — | — |
| t043 | text | — | ✓ | ✓ | — | — |
| t044 | text | — | ✓ | ✓ | — | — |
| t045 | text | — | ✓ | ✓ | — | — |
| t046 | text | — | ✓ | ✓ | — | — |
| t047 | text | — | ✗ | ✗ | — | — |
| t048 | text | — | ✓ | ✓ | — | — |
| t049 | text | — | ✓ | ✓ | — | — |
| t050 | text | — | ✓ | ✓ | — | — |
| t051 | text | — | ✓ | ✓ | — | — |
| t052 | text | — | ✓ | ✓ | — | — |
| t053 | text | — | ✓ | ✓ | — | — |
| t054 | text | — | ✓ | ✓ | — | — |
| t055 | text | — | ✓ | ✓ | — | — |
| t056 | text | — | ✗ | ✗ | — | — |
| t057 | text | — | ✓ | ✓ | — | — |
| t058 | text | — | ✗ | ✗ | — | — |
| t059 | text | — | ✓ | ✓ | — | — |
| t060 | text | — | ✓ | ✓ | — | — |
| t061 | text | — | ✓ | ✓ | — | — |
| t062 | text | — | ✓ | ✓ | — | — |
| t063 | text | — | ✓ | ✗ | — | — |
| t064 | text | — | ✓ | ✓ | — | — |
| t065 | text | — | ✓ | ✓ | — | — |
| t066 | text | — | ✓ | ✓ | — | — |
| t067 | text | — | ✗ | ✗ | — | — |
| t068 | text | — | ✓ | ✓ | — | — |
| t069 | text | — | ✓ | ✓ | — | — |
| t070 | text | — | ✓ | ✓ | — | — |
| t071 | text | — | ✓ | ✓ | — | — |
| t072 | text | — | ✓ | ✓ | — | — |
| t073 | text | — | ✓ | ✓ | — | — |
| t074 | text | — | ✓ | ✓ | — | — |
| t075 | text | — | ✓ | ✓ | — | — |
| t076 | text | — | ✗ | ✗ | — | — |
| t077 | text | — | ✗ | ✗ | — | — |
| t078 | text | — | ✗ | ✗ | — | — |
| t079 | text | — | ✓ | ✓ | — | — |
| t080 | text | — | ✓ | ✓ | — | — |
| t081 | text | — | ✓ | ✓ | — | — |
| t082 | text | — | ✗ | ✗ | — | — |
| t083 | text | — | ✓ | ✓ | — | — |
| t084 | text | — | ✓ | ✓ | — | — |
| t085 | text | — | ✗ | ✗ | — | — |
| t086 | text | — | ✗ | ✗ | — | — |
| t087 | text | — | ✓ | ✓ | — | — |
| t088 | text | — | ✗ | ✗ | — | — |
| t089 | text | — | ✗ | ✗ | — | — |
| t090 | text | — | ✗ | ✗ | — | — |
| t091 | text | — | ✓ | ✓ | — | — |
| t092 | text | — | ✗ | ✗ | — | — |
| t093 | text | — | — | — | — | — |
| t094 | text | — | — | — | — | — |
| t095 | text | — | — | — | — | — |
| t096 | text | — | — | — | — | — |
| t097 | text | — | — | — | — | — |
| t098 | text | — | — | — | — | — |
| t099 | text | — | — | — | — | — |
| t100 | text | — | — | — | — | — |
| v001 | chart | — | ✓ | ✓ | — | — |
| v002 | chart | — | ✓ | ✓ | — | — |
| v003 | chart | — | ✗ | ✗ | — | — |
| v004 | chart | — | ✗ | ✗ | — | — |
| v005 | chart | — | ✗ | ✗ | — | — |
| v006 | chart | — | ✓ | ✓ | — | — |
| v007 | chart | — | ✗ | ✗ | — | — |
| v008 | chart | — | ✓ | ✓ | — | — |
| v009 | chart | — | ✓ | ✗ | — | — |
| v010 | chart | — | ✗ | ✗ | — | — |
| v011 | table | — | ✗ | ✗ | — | — |
| v012 | table | — | ✓ | ✓ | — | — |
| v013 | table | — | ✗ | ✗ | — | — |
| v014 | table | — | ✗ | ✗ | — | — |
| v015 | table | — | ✓ | ✓ | — | — |
| v016 | table | — | ✓ | ✓ | — | — |
| v017 | table | — | ✗ | ✗ | — | — |
| v018 | table | — | ✗ | ✗ | — | — |
| v019 | table | — | ✗ | ✗ | — | — |
| v020 | table | — | ✗ | ✗ | — | — |
| v021 | table | — | ✗ | ✗ | — | — |
| v022 | table | — | ✗ | ✗ | — | — |
| v023 | diagram | — | ✗ | ✗ | — | — |
| v024 | diagram | — | ✓ | ✓ | — | — |
| v025 | diagram | — | ✗ | ✗ | — | — |
| v026 | diagram | — | ✗ | ✗ | — | — |
| v027 | scanned | — | ✗ | ✗ | — | — |
| v028 | scanned | — | ✓ | ✓ | — | — |
| v029 | scanned | — | ✓ | ✓ | — | — |
| v030 | chart | — | — | — | — | — |
