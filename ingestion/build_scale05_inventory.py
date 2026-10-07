from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

import httpx

from .expansion_sources import SOURCES
from .plan_inventory_chunks import plan as plan_chunks

SOURCES_SCOPE=("eurotechjobs","hnwhoishiring")
USER_AGENT="job-market-knowledge-graph/SCALE-05-inventory"


def build(out_dir: str, chunk_size: int = 250) -> dict:
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    per_source={}
    with httpx.Client(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent":USER_AGENT,"Accept-Language":"en,pl;q=0.8"},
    ) as client:
        for source in SOURCES_SCOPE:
            refs=SOURCES[source].discover(client,100000)
            source_rows=[
                {
                    "source":source,
                    "source_posting_id":str(ref.source_posting_id),
                    "url":ref.url,
                    "known":False,
                }
                for ref in refs
            ]
            source_rows.sort(key=lambda r:r["source_posting_id"])
            per_source[source]={
                "discoverable":len(source_rows),
                "known":0,
                "unknown":len(source_rows),
            }
            rows.extend(source_rows)
    rows.sort(key=lambda r:(r["source"],r["source_posting_id"]))
    raw=("\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":")) for r in rows)+"\n").encode("utf-8")
    comp=gzip.compress(raw,compresslevel=9,mtime=0)
    inventory=out/"inventory.jsonl.gz"
    inventory.write_bytes(comp)
    manifest={
        "format":"source-inventory-v1",
        "scope":"scale-05-eurotechjobs-hn",
        "sources":per_source,
        "discoverable_total":len(rows),
        "known_total":0,
        "unknown_total":len(rows),
        "uncompressed_bytes":len(raw),
        "compressed_bytes":len(comp),
        "uncompressed_sha256":hashlib.sha256(raw).hexdigest(),
        "compressed_sha256":hashlib.sha256(comp).hexdigest(),
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    plan_chunks(str(inventory),str(out/"chunks.json"),chunk_size)
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="data/inventories/scale-05")
    p.add_argument("--chunk-size",type=int,default=250)
    args=p.parse_args()
    print(json.dumps(build(args.out,args.chunk_size),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
