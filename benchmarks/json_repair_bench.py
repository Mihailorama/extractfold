"""Time parse_llm_json on truncated model answers.

Run: python benchmarks/json_repair_bench.py [rows]
Compares the built-in closer with json_repair (when installed) on a rows answer of
~*rows* line items cut at 25%, 50%, 75% and 99% of its length, plus the clean answer.
"""

from __future__ import annotations

import json
import sys
import time

from extractfold.parsing import _close_truncated, parse_llm_json


def answer(rows: int) -> str:
    items = [
        {"position": i, "name": f"Item {i} – работы по монтажу", "qty": i % 7 + 1,
         "price": round(i * 13.37, 2), "unit": "шт", "note": None}
        for i in range(rows)
    ]
    return json.dumps({"rows": items}, ensure_ascii=False)


def best_ms(fn, text: str, runs: int = 5) -> float:
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(text)
        times.append((time.perf_counter() - start) * 1000)
    return min(times)


def main() -> None:
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    full = answer(rows)
    try:
        import json_repair
    except ImportError:
        json_repair = None
    print(f"answer: {len(full):,} chars, {rows} rows")
    print("cut   | parse_llm_json ms | built-in ms | rows kept | json_repair ms | rows kept")
    for share in (0.25, 0.5, 0.75, 0.99, 1.0):
        text = full[: int(len(full) * share)]
        ms = best_ms(parse_llm_json, text)
        built_ms = best_ms(_close_truncated, text)
        kept = len(_close_truncated(text)["rows"]) if share < 1 else rows
        line = f"{share:>5.0%} | {ms:>17.1f} | {built_ms:>11.1f} | {kept:>9}"
        if json_repair is not None:
            repaired = json_repair.loads(text)
            line += f" | {best_ms(json_repair.loads, text):>14.1f} | {len(repaired['rows']):>9}"
        print(line)


if __name__ == "__main__":
    main()
