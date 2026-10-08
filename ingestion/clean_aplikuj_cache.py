"""Historical Aplikuj cleanup audit — permanently read-only.

The former title-based deletion was unsafe: a title is not evidence that a
recruitment is outside IT. `--apply` deliberately raises before any I/O mutation.
The prior deleted material is NOT recovered by this audit.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .aplikuj_it_scope import is_technical_it


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def compressed_rows(rows: list[dict]) -> tuple[bytes, dict]:
    raw = ("\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n").encode("utf-8")
    data = gzip.compress(raw, compresslevel=9, mtime=0)
    return data, {
        "rows": len(rows), "uncompressed_bytes": len(raw),
        "compressed_bytes": len(data), "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(data).hexdigest(),
    }


def clean(root: Path, evidence: Path, apply: bool = False) -> dict:
    if apply:
        raise RuntimeError("DISABLED: title-based deletion is forbidden; retain all IT-category candidates")
    report = {"mode": "HISTORICAL_READ_ONLY", "source": "aplikuj", "scope": "technical-it-v1", "before": 0,
              "title_signal": 0, "needs_review": 0, "chunks": 0, "failures": []}
    for manifest_path in sorted((root / "aplikuj").glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("scope") == "it-category-v2":
            continue  # the old heuristic does not apply to new evidence
        try:
            rows = read_gz(manifest_path.with_name("corpus.jsonl.gz"))
            signal = sum(is_technical_it(row["title"]) for row in rows)
            report["before"] += len(rows)
            report["title_signal"] += signal
            report["needs_review"] += len(rows) - signal
            report["chunks"] += 1
        except Exception as exc:
            report["failures"].append({"chunk": manifest_path.parent.name,
                                       "error": f"{type(exc).__name__}: {exc}"})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".local-crawl/scale-04")
    parser.add_argument("--evidence", default=".local-evidence/scale-04")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = clean(Path(args.root), Path(args.evidence), args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
