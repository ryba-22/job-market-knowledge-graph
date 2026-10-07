from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path

import psycopg


def export(dsn: str, out_dir: str) -> dict:
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    with psycopg.connect(dsn) as conn:
        rows=conn.execute(
            """
            select
                p.id,
                p.source_code,
                p.source_posting_id,
                p.canonical_source_url,
                r.id,
                r.title_source,
                r.source_projection_json,
                r.normalized_projection_json,
                r.normalized_content_hash,
                r.parser_version,
                r.normalizer_version,
                ro.payload_sha256,
                length(ro.payload_text),
                ro.transport_version,
                ro.archive_key,
                om.mention_text,
                om.normalized_mention
            from job_posting p
            join job_posting_revision r on r.id=p.current_revision_id
            join raw_observation ro on ro.id=r.raw_observation_id
            left join organization_mention om on om.job_posting_revision_id=r.id
            order by p.source_code,p.source_posting_id
            """
        ).fetchall()
    records=[]
    for row in rows:
        records.append({
            "source":row[1],
            "source_posting_id":row[2],
            "url":row[3],
            "revision_id":row[4],
            "title":row[5],
            "source_projection":row[6],
            "normalized_projection":row[7],
            "normalized_projection_hash":row[8],
            "parser_version":row[9],
            "normalizer_version":row[10],
            "raw_payload_sha256":row[11],
            "raw_payload_bytes":row[12],
            "transport_version":row[13],
            "archive_key":row[14],
            "organization_mention":row[15],
            "organization_mention_normalized":row[16],
        })
    raw=("\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":")) for r in records)+"\n").encode("utf-8")
    comp=gzip.compress(raw,compresslevel=9,mtime=0)
    corpus=out/"corpus.jsonl.gz"
    corpus.write_bytes(comp)
    by_source=Counter(r["source"] for r in records)
    manifest={
        "format":"market-corpus-v1",
        "postings":len(records),
        "by_source":dict(sorted(by_source.items())),
        "uncompressed_bytes":len(raw),
        "compressed_bytes":len(comp),
        "uncompressed_sha256":hashlib.sha256(raw).hexdigest(),
        "compressed_sha256":hashlib.sha256(comp).hexdigest(),
        "contains_raw_payload":False,
        "raw_payload_provenance":"Each record retains SHA-256, byte count and archive_key for the immutable RawObservation.",
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--out",default="reports/corpus-02")
    args=p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    print(json.dumps(export(args.dsn,args.out),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
