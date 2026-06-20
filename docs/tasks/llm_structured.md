---
purpose: "Provider-agnostic LLM structured-output extraction"
status: "OPEN"
priority: "P1"
created: "2026-06-20"
---

# Feature: llm_structured

## Problem
The highest-value extraction path is schema-guided structured output across Anthropic, OpenAI, and Gemini without leaking provider-specific payloads to callers.

## Proposed Solution
Add `LLMStructuredEngine` with Anthropic as the default provider, OpenAI and Gemini support, lazy SDK imports, provider-specific calls isolated behind methods, JSON parsing, schema validation, and cost metadata.

## Affected Files
- `src/extractfold/engines/llm_structured_engine.py` - provider adapter
- `pyproject.toml` - `extractfold[llm_structured]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed Anthropic call extracts JSON and validates it.
- [ ] OpenAI and Gemini provider branches parse tool/JSON-mode responses.
- [ ] Markdown/prose-wrapped JSON is recovered.

### Integration / E2E Tests
- [ ] Skipped integration tests document provider API key requirements.

### Test Commands
```bash
pytest tests/engines/test_llm_structured_engine.py -v
```

## Edge Cases
- Provider returns invalid JSON.
- Provider returns schema-shaped JSON plus explanatory text.

## Out of Scope
- Network calls in unit tests.
