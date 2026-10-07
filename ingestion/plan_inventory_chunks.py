from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


def plan(inventory_path: str, out_path: str, chunk_size: int) -> dict:
    rows=[
        json.loads(line)
        for line in gzip.decompress(Path(inventory_path).read_bytes()).decode("utf-8").split("\n")
        if line
    ]
    unknown=[r for r in rows if not r["known"]]
    by_source={}
    for row in unknown:
        by_source.setdefault(row["source"],[]).append(row)
    chunks=[]
    for source in sorted(by_source):
        source_rows=by_source[source]
        for idx in range(0,len(source_rows),chunk_size):
            part=source_rows[idx:idx+chunk_size]
            chunks.append({
                "source":source,
                "chunk_index":idx//chunk_size,
                "count":len(part),
                "first_source_posting_id":part[0]["source_posting_id"],
                "last_source_posting_id":part[-1]["source_posting_id"],
                "rows":part,
            })
    inventory_manifest_path = Path(inventory_path).with_name("manifest.json")
    inventory_manifest = json.loads(inventory_manifest_path.read_text(encoding="utf-8")) if inventory_manifest_path.exists() else {}
    result={
        "chunk_size":chunk_size,
        "unknown_total":len(unknown),
        "aplikuj_scope":inventory_manifest.get("aplikuj_scope"),
        "chunks":chunks,
        "chunks_by_source":{
            s:sum(1 for c in chunks if c["source"]==s)
            for s in sorted(by_source)
        },
    }
    Path(out_path).parent.mkdir(parents=True,exist_ok=True)
    Path(out_path).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--inventory",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--chunk-size",type=int,default=250)
    args=p.parse_args()
    result=plan(args.inventory,args.out,args.chunk_size)
    print(json.dumps({k:v for k,v in result.items() if k!="chunks"},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
