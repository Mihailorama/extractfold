# extractfold

`extractfold` is the structured-data sibling of `docfold`.

- `docfold`: document -> representation, such as Markdown, HTML, text, or layout.
- `extractfold`: document + JSON Schema -> schema-conformant Python `dict`.

The core package has no required third-party dependencies. Engines that need model
weights, cloud SDKs, or provider SDKs live behind optional extras and import those
dependencies lazily.

## Install

```bash
pip install extractfold
pip install "extractfold[provider_router]"
pip install "extractfold[llm_structured]"
pip install "extractfold[all]"
```

## Quick Start

```python
import asyncio

from extractfold.engines import LLMStructuredEngine

schema = {
    "type": "object",
    "required": ["invoice_id", "total"],
    "properties": {
        "invoice_id": {"type": "string"},
        "vendor": {"type": "string"},
        "total": {"type": "number"},
    },
}

async def main() -> None:
    result = await LLMStructuredEngine().extract("invoice.pdf", schema)
    print(result.data)

asyncio.run(main())
```

## CLI

```bash
extractfold extract invoice.pdf --schema invoice --engine llm_structured
extractfold extract invoice.pdf --schema schema.json --out result.json
extractfold compare invoice.pdf --schema schema.json --engines llm_structured,lift
extractfold list-engines
extractfold benchmark ./dataset --engines llm_structured,lift --out results.json
```

## Engine Comparison

| Engine | Type | License | Schema | Nested | Confidence | Provenance | Local/Remote | Speed | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `lift` | Datalab Lift adapter | SaaS | Native | Yes | Yes | Yes | Remote | Fast | Paid API |
| `nuextract` | Open model | Model license | Prompt JSON | Yes | No | No | Local | Medium | Hardware |
| `provider_router` | Injected model gateway | App-defined | Prompt JSON | Yes | No | No | Remote | App-defined | App-defined |
| `llm_structured` | LLM structured outputs | Provider terms | Tool/JSON mode | Yes | No | No | Remote | Medium | Paid tokens |
| `instructor` | Pydantic/JSON extraction | MIT library + provider terms | Pydantic/JSON Schema | Yes | No | No | Remote by default | Medium | Paid tokens |
| `llamaextract` | LlamaCloud Extract | SaaS | Native | Yes | No | No | Remote | Fast | Paid API |
| `azure_docint` | Azure Document Intelligence | SaaS | Query fields | Limited | Yes | Yes | Remote | Fast | Paid API |
| `google_docai` | Google Document AI | SaaS | Custom extractor/entities | Yes | Yes | Yes | Remote | Fast | Paid API |
| `textract` | AWS Textract | SaaS | QUERIES/FORMS | Limited | Yes | Yes | Remote | Fast | Paid API |
| `docfold_llm` | Composite | Mixed | LLM structured | Yes | Depends on LLM | Depends on LLM | Remote by default | Medium | Parse + token cost |

## How To Choose

| Need | Use |
| --- | --- |
| Existing model gateway, retries, and telemetry | `provider_router` |
| Best practical default for arbitrary schemas | `llm_structured` |
| First-party Datalab Lift workflow | `lift` |
| Local/open-model extraction | `nuextract` |
| Existing `instructor` stack | `instructor` |
| Managed extraction SaaS | `llamaextract` |
| Enterprise cloud OCR/forms/query fields | `azure_docint`, `google_docai`, or `textract` |
| Clean Markdown/text before extraction | `docfold_llm` |

## Engine Examples

```python
from extractfold.engines import (
    AzureDocIntEngine,
    DocfoldLLMEngine,
    GoogleDocAIEngine,
    InstructorEngine,
    LiftEngine,
    LLMStructuredEngine,
    LlamaExtractEngine,
    NuExtractEngine,
    ProviderRouterEngine,
    TextractEngine,
)
```

```python
async def provider_call(**kwargs):
    # Call an application-owned gateway and return JSON-compatible data.
    return {"invoice_id": "INV-001", "total": 125.5}

result = await ProviderRouterEngine(provider_call=provider_call).extract("invoice.txt", "invoice")
result = await LiftEngine().extract("invoice.pdf", "invoice")
result = await NuExtractEngine(backend="hf").extract("invoice.txt", "invoice")
result = await LLMStructuredEngine(provider="anthropic").extract("invoice.pdf", "invoice")
result = await LLMStructuredEngine(provider="openai").extract("invoice.pdf", "invoice")
result = await LLMStructuredEngine(provider="gemini").extract("invoice.pdf", "invoice")
result = await InstructorEngine().extract("invoice.pdf", "invoice")
result = await LlamaExtractEngine().extract("invoice.pdf", "invoice")
result = await AzureDocIntEngine().extract("invoice.pdf", "invoice")
result = await GoogleDocAIEngine().extract("invoice.pdf", "invoice")
result = await TextractEngine().extract("invoice.pdf", "invoice")
result = await DocfoldLLMEngine().extract("invoice.pdf", "invoice")
```

## Evaluation

`extractfold.evaluation` scores prediction folders shaped like this:

```text
dataset/
  gold/invoice.json
  predictions/llm_structured/invoice.json
  predictions/lift/invoice.json
```

Metrics include field accuracy, schema compliance, precision/recall/F1,
hallucination rate, type correctness, normalized value matching, and nested array
alignment.

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/
mypy src/
pytest tests/ -m "not integration"
```
