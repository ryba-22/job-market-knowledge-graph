"""Remove out-of-scope Aplikuj postings and their raw payloads from local crawl.

Only complete chunks are rewritten. Historical discovery inventory is left
untouched as provenance; it must not be used to resume IT-only crawling.
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


def replace_bytes(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + ".scoped-tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def clean(root: Path, evidence: Path, apply: bool = False) -> dict:
    report = {"mode": "APPLIED" if apply else "DRY_RUN", "source": "aplikuj", "scope": "technical-it-v1", "before": 0, "kept": 0, "removed": 0, "chunks": 0, "failures": []}
    for manifest_path in sorted((root / "aplikuj").glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        d = manifest_path.parent
        corpus_path = d / "corpus.jsonl.gz"
        raw_path = evidence / "aplikuj" / d.name / "raw-observations.jsonl.gz"
        try:
            if manifest.get("errors"):
                raise ValueError("chunk has errors")
            corpus = read_gz(corpus_path)
            raw = read_gz(raw_path)
            previous_excluded = int(manifest.get("excluded_non_it", 0))
            if int(manifest["postings"]) != len(corpus):
                raise ValueError("corpus manifest mismatch")
            keep = [r for r in corpus if is_technical_it(r["title"], (r.get("source_projection") or {}).get("industry"))]
            excluded_ids = {str(r["source_posting_id"]) for r in corpus if not is_technical_it(r["title"], (r.get("source_projection") or {}).get("industry"))}
            raw_keep = [r for r in raw if str(r["source_posting_id"]) not in excluded_ids]
            if len(raw) - len(raw_keep) != len(excluded_ids):
                raise ValueError("raw payload mismatch: not deleting without one-to-one identity")
            if int(manifest["planned"]) != len(corpus) + int(manifest.get("source_gone", 0)) + previous_excluded:
                raise ValueError("incomplete chunk; must not rewrite")
            report["before"] += len(corpus)
            report["kept"] += len(keep)
            report["removed"] += len(excluded_ids)
            report["chunks"] += 1
            if not apply or not excluded_ids:
                continue
            cb, cm = compressed_rows(keep)
            rb, rm = compressed_rows(raw_keep)
            manifest["postings"] = len(keep)
            manifest["by_source"] = {"aplikuj": len(keep)} if keep else {}
            manifest["excluded_non_it"] = previous_excluded + len(excluded_ids)
            manifest["scope"] = "technical-it-v1"
            manifest["corpus"] = cm
            manifest["raw_archive"] = rm
            replace_bytes(corpus_path, cb)
            replace_bytes(raw_path, rb)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report["failures"].append({"chunk": d.name, "error": f"{type(exc).__name__}: {exc}"})
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
