# Benchmarks

## Dataset Shape

```text
dataset/
  invoice.pdf
  invoice.schema.json
  invoice.gold.json
```

Run:

```bash
extractfold benchmark dataset --engines llm_structured,lift --out results.json
```

## Capability Matrix

| Engine | Confidence | Provenance | Nested | Local | Remote | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| lift | Yes | Yes | Yes | No | Yes | Reference SaaS adapter |
| nuextract | No | No | Yes | Yes | No | Requires local HF/vLLM runtime |
| provider_router | Yes | Yes | Yes | No | Yes | Injected callable; provenance with `source_catalog=`; cost and latency come from caller metadata |
| llm_structured | No | No | Yes | No | Yes | Anthropic default; OpenAI/Gemini supported |
| instructor | No | No | Yes | No | Yes | Uses provider chat model through instructor |
| llamaextract | No | No | Yes | No | Yes | LlamaCloud Extract |
| azure_docint | Yes | Yes | Limited | No | Yes | Query-field/form extraction |
| google_docai | Yes | Yes | Yes | No | Yes | Processor/entity extraction |
| textract | Yes | Yes | Limited | No | Yes | AnalyzeDocument QUERIES/FORMS |
| docfold_llm | Depends | Depends | Yes | No | Yes | docfold text then LLM extraction |

## Cost And Hardware

- Local NuExtract cost is GPU/CPU runtime and model storage.
- Cloud engines bill per page, request, or token according to provider terms.
- Benchmark reports include `latency_ms` and `cost_usd` when engines populate cost metadata.

## Truncated JSON answers

`python benchmarks/json_repair_bench.py 2000` cuts a 2,000-row answer (~233k characters)
at several points and times `parse_llm_json`, its built-in closer and `json_repair`.
Best of 5 runs, shared Linux VPS, Python 3.12, json_repair and orjson 3.13 installed
(2026-11-12):

| Cut | parse_llm_json ms | built-in ms | rows kept | json_repair ms | rows kept |
| --- | --- | --- | --- | --- | --- |
| 25% | 10.9 | 9.7 | 509 | 170.3 | 509 |
| 50% | 82.3 | 96.4 | 1012 | 167.8 | 1013 |
| 75% | 31.1 | 37.5 | 1506 | 161.4 | 1507 |
| 99% | 62.6 | 41.0 | 1980 | 421.2 | 1981 |
| 100% (clean) | 2.1 | - | 2000 | 4.8 | 2000 |

The built-in closer keeps only complete rows; `json_repair` also keeps the half-written
last row. Timings on a loaded machine vary by about 2x between runs.
