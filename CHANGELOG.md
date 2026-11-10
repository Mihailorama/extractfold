# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
