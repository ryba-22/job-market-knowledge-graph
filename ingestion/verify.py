from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .storage import PostgresStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--min-per-source", type=int, default=50)
    parser.add_argument("--report", default="reports/crawl-02-verification.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    summary = PostgresStore(args.dsn).summary()
    failures = []
    for source in ("theprotocol", "justjoinit"):
        actual = summary["by_source"].get(source, 0)
        if actual < args.min_per_source:
            failures.append(f"{source}: expected >= {args.min_per_source}, got {actual}")

    unchanged = summary["lifecycle"].get("UNCHANGED", 0)
    expected_total = args.min_per_source * 2
    if unchanged < expected_total:
        failures.append(
            f"recrawl evidence: expected >= {expected_total} UNCHANGED observations, got {unchanged}"
        )

    if summary["revisions"] < expected_total:
        failures.append(
            f"expected >= {expected_total} revisions after first crawl, got {summary['revisions']}"
        )

    result = {
        "pass": not failures,
        "failures": failures,
        "summary": summary,
        "assertions": {
            "min_per_source": args.min_per_source,
            "recrawl_unchanged_min": expected_total,
            "destructive_deduplication": False,
        },
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
