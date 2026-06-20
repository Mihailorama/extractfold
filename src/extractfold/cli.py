"""extractfold CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from extractfold.engines.base import ExtractionResult, ExtractionRouter, load_schema


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="extractfold",
        description="Extract schema-conformant dictionaries from documents.",
    )
    sub = parser.add_subparsers(dest="command")

    extract_p = sub.add_parser("extract", help="Extract structured data from a document")
    extract_p.add_argument("file")
    extract_p.add_argument("--schema", required=True)
    extract_p.add_argument("--engine")
    extract_p.add_argument("--out")
    extract_p.add_argument("--format", choices=["json"], default="json")

    compare_p = sub.add_parser("compare", help="Compare engines on a document")
    compare_p.add_argument("file")
    compare_p.add_argument("--schema", required=True)
    compare_p.add_argument("--engines")

    sub.add_parser("list-engines", help="List registered engines")

    benchmark_p = sub.add_parser("benchmark", help="Run the benchmark harness")
    benchmark_p.add_argument("dataset")
    benchmark_p.add_argument("--engines")
    benchmark_p.add_argument("--out")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        raise SystemExit(0)
    if args.command == "extract":
        asyncio.run(_cmd_extract(args))
    elif args.command == "compare":
        asyncio.run(_cmd_compare(args))
    elif args.command == "list-engines":
        _cmd_list_engines()
    elif args.command == "benchmark":
        _run_benchmark_cli(args)


def _build_router() -> ExtractionRouter:
    from extractfold.engines.azure_docint_engine import AzureDocIntEngine
    from extractfold.engines.docfold_llm_engine import DocfoldLLMEngine
    from extractfold.engines.google_docai_engine import GoogleDocAIEngine
    from extractfold.engines.instructor_engine import InstructorEngine
    from extractfold.engines.lift_engine import LiftEngine
    from extractfold.engines.llamaextract_engine import LlamaExtractEngine
    from extractfold.engines.llm_structured_engine import LLMStructuredEngine
    from extractfold.engines.nuextract_engine import NuExtractEngine
    from extractfold.engines.textract_engine import TextractEngine

    return ExtractionRouter(
        [
            LiftEngine(),
            NuExtractEngine(),
            LLMStructuredEngine(),
            InstructorEngine(),
            LlamaExtractEngine(),
            AzureDocIntEngine(),
            GoogleDocAIEngine(),
            TextractEngine(),
            DocfoldLLMEngine(),
        ]
    )


async def _cmd_extract(args: argparse.Namespace) -> None:
    router = _build_router()
    schema = load_schema(args.schema)
    result = await router.extract(args.file, schema, engine_hint=args.engine)
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        print(payload)


async def _cmd_compare(args: argparse.Namespace) -> None:
    router = _build_router()
    schema = load_schema(args.schema)
    engines = args.engines.split(",") if args.engines else None
    results = await router.compare(args.file, schema, engines=engines)
    print("Engine results")
    print("--------------")
    for name, result in results.items():
        print(f"{name}: valid={result.valid} data={json.dumps(result.data, ensure_ascii=False)}")
    print()
    print("Field agreement")
    print("---------------")
    for field, values in _field_agreement(results).items():
        print(f"{field}: {values}")


def _cmd_list_engines() -> None:
    engines = _build_router().list_engines()
    print(
        f"{'Engine':<16} {'Avail':<6} {'Conf':<4} {'Prov':<4} "
        f"{'Nest':<4} {'Local':<5} {'Remote':<6} Extensions"
    )
    print("-" * 86)
    for engine in engines:
        caps = engine["capabilities"]
        print(
            f"{engine['name']:<16} {str(engine['available']):<6} "
            f"{_mark(caps['field_confidence']):<4} {_mark(caps['provenance']):<4} "
            f"{_mark(caps['nested_schemas']):<4} {_mark(caps['local']):<5} "
            f"{_mark(caps['remote']):<6} {', '.join(engine['extensions'][:8])}"
        )


def _run_benchmark_cli(args: argparse.Namespace) -> None:
    import benchmark

    engines = args.engines.split(",") if args.engines else None
    report = asyncio.run(
        benchmark.run_benchmark(
            args.dataset,
            engines=engines,
            router=_build_router(),
            output_path=args.out,
        )
    )
    print(report.to_table())


def _field_agreement(results: dict[str, ExtractionResult]) -> dict[str, dict[str, Any]]:
    fields = sorted({field for result in results.values() for field in result.data})
    agreement: dict[str, dict[str, Any]] = {}
    for field in fields:
        values = {engine: result.data.get(field) for engine, result in results.items()}
        unique = {json.dumps(value, sort_keys=True) for value in values.values()}
        agreement[field] = {"agree": len(unique) <= 1, "values": values}
    return agreement


def _mark(value: bool) -> str:
    return "+" if value else "-"


if __name__ == "__main__":
    main(sys.argv[1:])
