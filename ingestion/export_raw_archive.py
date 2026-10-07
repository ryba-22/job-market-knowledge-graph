from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

import psycopg


def export(dsn: str, source: str, out_dir: str):
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            select
                source_code,source_posting_id,requested_url,final_url,http_status,
                content_type,payload_sha256,payload_text,run_id,parser_version,
                transport_version,archive_key,fetched_at
            from raw_observation
            where source_code=%s
            order by source_posting_id,id
            """,
            (source,),
        ).fetchall()

    records = [
        {
            "source": r[0],
            "source_posting_id": r[1],
            "requested_url": r[2],
            "final_url": r[3],
            "http_status": r[4],
            "content_type": r[5],
            "payload_sha256": r[6],
            "payload_text": r[7],
            "run_id": r[8],
            "parser_version": r[9],
            "transport_version": r[10],
            "archive_key": r[11],
            "fetched_at": r[12].isoformat() if r[12] else None,
        }
        for r in rows
    ]

    raw = (
        "\n".join(
            json.dumps(
                x,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for x in records
        )
        + "\n"
    ).encode("utf-8")
    comp = gzip.compress(raw, compresslevel=9, mtime=0)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw-observations.jsonl.gz").write_bytes(comp)

    manifest = {
        "source": source,
        "observations": len(records),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(comp),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(comp).hexdigest(),
    }
    (out / "raw-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    print(json.dumps(export(args.dsn, args.source, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
