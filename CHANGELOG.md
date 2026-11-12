# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `parse_llm_json(text) -> (data, repaired)`: orjson (when installed) then stdlib parsing;
  on failure a built-in closer cuts a truncated answer back to its last complete element
  (5-10x faster than json_repair on large answers), and `json_repair` handles other damage
  when installed. New `fast_json` extra (`orjson`, `json_repair`).
- `ProviderRouterEngine(repair_json=True)` repairs an unparseable answer instead of moving
  to the next model (`metadata["repaired"]`).
- `benchmarks/json_repair_bench.py` and results in `docs/benchmarks.md`.
- Per-field provenance and confidence in `ProviderRouterEngine`:
  `build_source_catalog(text, input_format=, blocks=)` lists citable cells (sheet, CSV),
  layout blocks with page and bbox (docfold `bounding_boxes`), HTML blocks with page, JSON
  values or paragraphs. Passing `source_catalog=` adds the catalog and citation rules to
  the prompt; `result.provenance` holds per field `source_refs` (locations), `confidence`
  and `rationale`, re-scored against the cited text by `align_provenance`;
  `field_confidence` is the mean per field.
- `extract_rows_chunked(source_catalog=)` gives each chunk only its own entries and keeps
  `provenance["rows"]` aligned with `data["rows"]`.

### Changed
- `ProviderRouterEngine.capabilities` now declares `provenance` and `field_confidence`.
- `chunk_document(text, input_format=, max_chars=, max_rows=)`: format-aware chunks
  that never cut a row, line or page: spreadsheet text (`Sheet: <name>` sections, per-sheet
  row ranges, carried-over sheet and section-header `context`), CSV (quote-aware, header
  on every chunk), JSON arrays, HTML page nodes, Markdown sections; each chunk has
  `estimated_rows`.
- `chunk_budget(text, max_input_tokens=, max_output_tokens=)`: `max_chars` / `max_rows`
  from a model's limits.
- `extract_rows_chunked(input_format=, max_rows=)` plans chunks with `chunk_document`;
  a JSON array of objects that already uses only the schema's fields passes through
  without a model call (`metadata["passthrough"]`).
- `prescan(text, llm=)`: one call over the document's head and tail returns a `PreScan`
  (columns, types, structure, control values, `expected_rows`, prompt `context()`).
- `extract_rows_chunked(prescan=, rerun_below=, rerun_engine=)`: the pre-scan context
  reaches every chunk call as `context=`; chunks returning fewer rows than expected are
  re-run and the longer answer kept. Per chunk `expected_rows` / `rerun`, in the summary
  `rerun_chunks`, and `metadata["row_count"]` / `metadata["prescan"]`.
- `ProviderRouterEngine`'s default prompt includes a `context=` argument.
- `check_rows(rows, columns=, expected_rows=)`: row-count, schema-compliance and
  suspicious-pattern checks as a uniform list of `{check, status, message}`.
- `extract_rows_chunked` reports per chunk `checks` and `truncated`, plus
  `chunking["truncated_chunks"]`.
- `ProviderRouterEngine` reads chat-completion answers and `{"content", "finish_reason"}`
  dicts; an answer cut at the token limit is kept when it parses
  (`metadata["truncated"]`), otherwise the next model is tried.
- `ProviderRouterEngine(raise_on_error=False)`: when the last model fails, an invalid
  result with `metadata["error"] = {"stage": "llm", "model", "message"}`; chunked
  extraction records it on the chunk and goes on.

## [0.2.0] - 2026-11-11

### Added
- `ProviderRouterEngine(models=[...])`: ordered cross-provider fallback chain; a model
  that raises or answers without parseable JSON hands the call to the next one.
  `metadata["model"]` / `metadata["fallbacks"]` report which model answered.
- `extract_rows_chunked(..., dedupe=False)` keeps identical rows (repeated line items);
  `concurrency=N` extracts N chunks at once, rows stay in chunk order.

## [0.1.1] - 2026-08-20

### Fixed
- Publish releases through a dedicated OIDC PyPI workflow so release tags do
  not depend on the general test workflow.

## [0.1.0] - 2026-08-19

### Added
- `fenic` engine adapter for typedef-ai's fenic `semantic.extract`, behind the
  `extractfold[fenic]` extra.
- Initial extractfold package scaffold with schema-first engine contract.
- Router, CLI, evaluation runner, benchmark harness, docs, packaging, and CI.
- Engine adapters for Lift, NuExtract, LLM structured outputs, Instructor,
  LlamaExtract, Azure Document Intelligence, Google Document AI, AWS Textract,
  and docfold plus LLM extraction.
- Dependency-free `provider_router` engine for injected model gateways over
  prepared text.
- Opt-in resilient chunk execution for `extract_rows_chunked(..., continue_on_error=True)`.

### Fixed
- Exclude `.claude` from the sdist; its out-of-tree symlinks broke building a
  wheel from the sdist.
