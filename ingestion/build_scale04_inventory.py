from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import httpx

from .expansion_sources import SOURCES
from .scale_acquisition import load_known_ids

SOURCES_SCOPE=("aplikuj","itleaders","michaelpage")
USER_AGENT="job-market-knowledge-graph/SCALE-04-inventory"


def build(base_corpus: str, out_dir: str) -> dict:
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    all_rows=[]
    per_source={}
    with httpx.Client(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent":USER_AGENT,"Accept-Language":"pl,en;q=0.8"},
    ) as client:
        for source in SOURCES_SCOPE:
            refs=SOURCES[source].discover(client,100000)
            known=set() if source == "aplikuj" else load_known_ids(base_corpus,source)
            if source == "aplikuj":
                # Never treat the 33 title-pruned v1 survivors as v2-complete.
                # Only fully accounted, assessment-backed v2 chunks may be reused.
                from .run_file_backed_plan import _manifest_ok
                root = Path(".local-crawl/scale-04-it-v2/aplikuj")
                for manifest in root.glob("*/manifest.json"):
                    if not _manifest_ok(manifest, expected_scope="it-category-v2"):
                        continue
                    with gzip.open(manifest.with_name("corpus.jsonl.gz"), "rt", encoding="utf-8") as handle:
                        known.update(str(json.loads(line)["source_posting_id"]) for line in handle if line.strip())
            rows=[
                {
                    "source":source,
                    "source_posting_id":str(ref.source_posting_id),
                    "url":ref.url,
                    "known":str(ref.source_posting_id) in known,
                }
                for ref in refs
            ]
            rows.sort(key=lambda r:r["source_posting_id"])
            per_source[source]={
                "discoverable":len(rows),
                "known":sum(1 for r in rows if r["known"]),
                "unknown":sum(1 for r in rows if not r["known"]),
            }
            all_rows.extend(rows)
    all_rows.sort(key=lambda r:(r["source"],r["source_posting_id"]))
    raw=("\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":")) for r in all_rows)+"\n").encode("utf-8")
    comp=gzip.compress(raw,compresslevel=9,mtime=0)
    (out/"inventory.jsonl.gz").write_bytes(comp)
    manifest={
        "format":"source-inventory-v1",
        "scope":"scale-04-more-direct-sources-it-only",
        "aplikuj_scope":"it-category-v2",
        "base_corpus":base_corpus,
        "sources":per_source,
        "discoverable_total":sum(v["discoverable"] for v in per_source.values()),
        "known_total":sum(v["known"] for v in per_source.values()),
        "unknown_total":sum(v["unknown"] for v in per_source.values()),
        "uncompressed_bytes":len(raw),
        "compressed_bytes":len(comp),
        "uncompressed_sha256":hashlib.sha256(raw).hexdigest(),
        "compressed_sha256":hashlib.sha256(comp).hexdigest(),
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base-corpus",default="data/corpora/corpus-08-partial/corpus.jsonl.gz")
    p.add_argument("--out",default="reports/scale-04-inventory")
    args=p.parse_args()
    print(json.dumps(build(args.base_corpus,args.out),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
