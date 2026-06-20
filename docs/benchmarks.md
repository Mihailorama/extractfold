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
