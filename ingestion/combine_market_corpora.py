from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

def read_corpus(path: Path) -> list[dict]:
    raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]

def combine(base: Path, expansion: Path, out_dir: Path) -> dict:
    records = {}
    for record in read_corpus(base) + read_corpus(expansion):
        records[(record["source"], record["source_posting_id"])] = record
    ordered = [records[key] for key in sorted(records)]
    raw = ("\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for r in ordered
    ) + "\n").encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus.jsonl.gz").write_bytes(compressed)
    by_source = Counter(r["source"] for r in ordered)
    manifest = {
        "format": "market-corpus-v2-multisource",
        "postings": len(ordered),
        "by_source": dict(sorted(by_source.items())),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(compressed),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "base_corpus": str(base),
        "expansion_corpus": str(expansion),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--expansion", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    print(json.dumps(
        combine(Path(args.base), Path(args.expansion), Path(args.out)),
        ensure_ascii=False,
        indent=2,
    ))

if __name__ == "__main__":
    main()
