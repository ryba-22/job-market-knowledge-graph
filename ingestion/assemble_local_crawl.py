from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from .run_file_backed_plan import _manifest_ok


def _read_gz(path: Path):
    return [
        json.loads(line)
        for line in gzip.decompress(path.read_bytes()).decode("utf-8").split("\n")
        if line
    ]


def assemble(base_path: str, plan_path: str, crawl_root: str, out_dir: str, version: str) -> dict:
    base = Path(base_path)
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    root = Path(crawl_root)
    rows = {(r["source"], str(r["source_posting_id"])): r for r in _read_gz(base)}
    base_count = len(rows)
    new_count = 0
    source_gone = 0
    incomplete = []
    components = []

    for chunk in plan["chunks"]:
        source = chunk["source"]
        idx = int(chunk["chunk_index"])
        directory = root / source / str(idx)
        manifest_path = directory / "manifest.json"
        if not _manifest_ok(manifest_path):
            incomplete.append(f"{source}:{idx}")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        corpus_path = directory / "corpus.jsonl.gz"
        chunk_rows = _read_gz(corpus_path)
        if len(chunk_rows) != int(manifest["postings"]):
            raise RuntimeError(f"chunk corpus/manifest mismatch: {source}:{idx}")
        source_gone += int(manifest.get("source_gone", 0))
        for row in chunk_rows:
            key = (row["source"], str(row["source_posting_id"]))
            prior = rows.get(key)
            if prior is not None and prior != row:
                raise RuntimeError(f"conflicting duplicate source identity: {key}")
            if prior is None:
                rows[key] = row
                new_count += 1
        components.append({
            "source": source,
            "chunk_index": idx,
            "planned": int(manifest["planned"]),
            "postings": int(manifest["postings"]),
            "source_gone": int(manifest.get("source_gone", 0)),
            "corpus_sha256": manifest["corpus"]["compressed_sha256"],
        })

    if incomplete:
        raise RuntimeError(f"incomplete crawl: {len(incomplete)} chunks; first={incomplete[:10]}")

    ordered = [rows[k] for k in sorted(rows)]
    raw = ("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in ordered) + "\n").encode("utf-8")
    comp = gzip.compress(raw, compresslevel=9, mtime=0)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "corpus.jsonl.gz").write_bytes(comp)
    by_source = Counter(r["source"] for r in ordered)
    manifest = {
        "format": "market-corpus-v1",
        "corpus_version": version,
        "postings": len(ordered),
        "base_postings": base_count,
        "new_postings": new_count,
        "source_gone": source_gone,
        "planned_unknown": int(plan.get("unknown_total", 0)),
        "chunks": len(plan["chunks"]),
        "by_source": dict(sorted(by_source.items())),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(comp),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(comp).hexdigest(),
        "components": components,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--crawl-root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--version", required=True)
    args = p.parse_args()
    print(json.dumps(assemble(args.base, args.plan, args.crawl_root, args.out, args.version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
