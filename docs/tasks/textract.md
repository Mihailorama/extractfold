---
purpose: "AWS Textract extraction adapter"
status: "OPEN"
priority: "P2"
created: "2026-06-20"
---

# Feature: textract

## Problem
AWS Textract `AnalyzeDocument` supports forms and query fields that should normalize into extractfold's result contract.

## Proposed Solution
Add `TextractEngine` with lazy boto3 imports, query generation from schema, `AnalyzeDocument` parsing, and confidence/provenance maps.

## Affected Files
- `src/extractfold/engines/textract_engine.py` - adapter
- `pyproject.toml` - `extractfold[textract]` extra

## Test Plan

### Unit / Functional Tests
- [ ] Stubbed Textract query results map to extracted data.
- [ ] Availability requires boto3 and credentials.

### Integration / E2E Tests
- [ ] Skipped real AWS run.

### Test Commands
```bash
pytest tests/engines/test_textract_engine.py -v
```

## Edge Cases
- Textract responses can use QUERY_RESULT, KEY_VALUE_SET, or WORD blocks.

## Out of Scope
- Async S3 workflows for large PDFs.
