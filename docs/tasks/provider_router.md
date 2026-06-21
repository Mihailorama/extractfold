---
purpose: "Add a dependency-free provider-router extraction adapter for prepared text."
status: "OPEN"
priority: "P1"
created: "2026-06-21"
---

# Feature: provider_router

## Problem
Production callers often already have a model gateway, retry policy, tracing, and
cost controls. They need extractfold to own schema loading, prompt construction,
payload parsing, validation, and router integration without forcing another SDK
or provider dependency into the core package.

## Proposed Solution
Add a `provider_router` engine that accepts an injected callable for schema-guided
text extraction. The engine will:

- Preserve the `ExtractionEngine` contract and return `ExtractionResult`.
- Support text-oriented files and direct `text=` overrides.
- Build a schema-first extraction prompt by default, with an override hook.
- Pass source text, schema, provider, model, prompt, and arbitrary kwargs to the
  injected callable.
- Parse common JSON payload shapes and validate against the supplied schema.
- Copy structured usage, cost, and routing metadata into `ExtractionResult.metadata`
  when the callable returns it.
- Declare remote, nested-schema, and batch capabilities honestly.

## Affected Files
- `src/extractfold/engines/provider_router_engine.py` - new adapter.
- `src/extractfold/engines/__init__.py` - export the adapter.
- `src/extractfold/engines/base.py` - include the adapter in text routing priority.
- `src/extractfold/cli.py` - register the adapter in the default router.
- `pyproject.toml` - declare a dependency-free `provider_router` extra.
- `tests/engines/test_provider_router_engine.py` - stubbed engine tests.
- `tests/engines/test_engine_roster.py` - default roster coverage.
- `tests/engines/test_router.py` - text priority coverage.
- `tests/test_packaging.py` - extras coverage.

## Test Plan

### Unit / Functional Tests
- [ ] Availability is true only when an injected provider callable is supplied.
- [ ] The callable receives text, schema, prompt, provider, model, and kwargs.
- [ ] String and wrapped JSON payloads are parsed and validated.
- [ ] Usage, cost, and routing details are copied to metadata.
- [ ] The default router registers `provider_router`.
- [ ] Text routing prefers `provider_router` when available.

### Integration / E2E Tests
- [ ] Skipped integration placeholder for a real provider-router call.

### Test Commands
```bash
pytest tests/engines/test_provider_router_engine.py -v
pytest tests/engines/test_router.py -v
pytest tests/ -m "not integration"
```

## Edge Cases
- Callable can be sync or async.
- Callable can return a raw JSON string, a JSON object, or an object with a
  `model_dump()` method.
- The engine must not import provider SDKs or add base dependencies.
- Schema validation failure must be visible through `ExtractionResult.valid`.

## Out of Scope
- Owning provider credentials, retries, rate limits, or telemetry.
- Adding a new SDK dependency to the core package.
