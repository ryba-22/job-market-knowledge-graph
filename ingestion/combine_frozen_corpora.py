from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path


def _read(path: Path):
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode("utf-8").splitlines() if line]


def combine(base_path: str, expansion_path: str, out_dir: str, version: str) -> dict:
    base=Path(base_path)
    expansion=Path(expansion_path)
    rows={}
    component_counts={}
    for component,path in (("base",base),("expansion",expansion)):
        source_rows=_read(path)
        component_counts[component]=len(source_rows)
        for row in source_rows:
            key=(row["source"],row["source_posting_id"])
            prior=rows.get(key)
            if prior is not None and prior != row:
                raise RuntimeError(f"conflicting duplicate source identity: {key}")
            rows[key]=row
    ordered=[rows[k] for k in sorted(rows)]
    raw=("\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":")) for r in ordered)+"\n").encode("utf-8")
    comp=gzip.compress(raw,compresslevel=9,mtime=0)
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"corpus.jsonl.gz").write_bytes(comp)
    by_source=Counter(r["source"] for r in ordered)
    manifest={
        "format":"market-corpus-v1",
        "corpus_version":version,
        "postings":len(ordered),
        "by_source":dict(sorted(by_source.items())),
        "uncompressed_bytes":len(raw),
        "compressed_bytes":len(comp),
        "uncompressed_sha256":hashlib.sha256(raw).hexdigest(),
        "compressed_sha256":hashlib.sha256(comp).hexdigest(),
        "components":{
            "base":{"path":str(base),"postings":component_counts["base"]},
            "expansion":{"path":str(expansion),"postings":component_counts["expansion"]},
        },
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base",required=True)
    p.add_argument("--expansion",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--version",required=True)
    args=p.parse_args()
    print(json.dumps(combine(args.base,args.expansion,args.out,args.version),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
