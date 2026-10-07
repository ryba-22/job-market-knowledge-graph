from __future__ import annotations

import argparse
from collections import Counter
import glob
import gzip
import hashlib
import json
from pathlib import Path


def _read(path: Path):
    return [
        json.loads(x)
        for x in gzip.decompress(path.read_bytes()).decode("utf-8").splitlines()
        if x
    ]


def assemble(base_path: str, slice_paths: list[str], out_dir: str, version: str):
    rows = {}
    components = []

    all_parts = [("base", Path(base_path))]
    all_parts.extend(("slice", Path(p)) for p in slice_paths)

    for role, path in all_parts:
        source_rows = _read(path)
        components.append(
            {
                "role": role,
                "path": str(path),
                "postings": len(source_rows),
                "compressed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

        for row in source_rows:
            key = (row["source"], row["source_posting_id"])
            prior = rows.get(key)
            if prior is not None and prior != row:
                raise RuntimeError(f"conflicting duplicate source identity: {key}")
            rows[key] = row

    ordered = [rows[k] for k in sorted(rows)]
    raw = (
        "\n".join(
            json.dumps(
                r,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for r in ordered
        )
        + "\n"
    ).encode("utf-8")
    comp = gzip.compress(raw, compresslevel=9, mtime=0)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "corpus.jsonl.gz").write_bytes(comp)

    manifest = {
        "format": "market-corpus-v1",
        "corpus_version": version,
        "postings": len(ordered),
        "by_source": dict(sorted(Counter(r["source"] for r in ordered).items())),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(comp),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(comp).hexdigest(),
        "components": components,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--slice-glob", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--version", required=True)
    args = p.parse_args()

    slices = sorted(glob.glob(args.slice_glob))
    if not slices:
        raise SystemExit(f"no slices matched {args.slice_glob}")

    print(
        json.dumps(
            assemble(args.base, slices, args.out, args.version),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
