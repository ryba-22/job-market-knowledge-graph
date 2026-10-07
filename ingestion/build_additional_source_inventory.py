from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import httpx

from .expansion_sources import SOURCES

SOURCES_TO_INVENTORY=("solidjobs","teamquest")
USER_AGENT="job-market-knowledge-graph/SCALE-03-inventory"


def build(out_dir: str):
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    summary={}
    with httpx.Client(timeout=60,follow_redirects=True,headers={"User-Agent":USER_AGENT}) as client:
        for source in SOURCES_TO_INVENTORY:
            refs=SOURCES[source].discover(client,100000)
            summary[source]={"discoverable":len(refs),"unknown":len(refs)}
            for ref in refs:
                rows.append({
                    "source":source,
                    "source_posting_id":str(ref.source_posting_id),
                    "url":ref.url,
                    "known":False,
                })
    rows.sort(key=lambda r:(r["source"],r["source_posting_id"]))
    raw=("\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":")) for r in rows)+"\n").encode("utf-8")
    comp=gzip.compress(raw,compresslevel=9,mtime=0)
    (out/"inventory.jsonl.gz").write_bytes(comp)
    manifest={
        "format":"source-inventory-v1",
        "sources":summary,
        "discoverable_total":len(rows),
        "unknown_total":len(rows),
        "uncompressed_sha256":hashlib.sha256(raw).hexdigest(),
        "compressed_sha256":hashlib.sha256(comp).hexdigest(),
        "uncompressed_bytes":len(raw),
        "compressed_bytes":len(comp),
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="data/inventories/scale-03")
    args=p.parse_args()
    print(json.dumps(build(args.out),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
