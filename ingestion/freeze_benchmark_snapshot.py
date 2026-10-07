from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def freeze(dsn: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    postings_dir = out_dir / "postings"
    postings_dir.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(dsn) as conn:
        pairs = conn.execute(
            """
            select
                e.id,
                e.posting_a_id,
                e.posting_b_id,
                e.stratum,
                e.features_json,
                e.evidence_json,
                d.label,
                d.basis,
                d.rationale,
                d.evidence_snapshot_json
            from er_eval_pair e
            join lateral (
                select label,basis,rationale,evidence_snapshot_json
                from er_adjudication_decision
                where er_eval_pair_id=e.id
                order by created_at desc,id desc limit 1
            ) d on true
            order by e.id
            """
        ).fetchall()
        posting_ids=sorted({pid for r in pairs for pid in (r[1],r[2])})
        postings={}
        for posting_id in posting_ids:
            row=conn.execute(
                """
                select
                    p.id,p.source_code,p.source_posting_id,p.canonical_source_url,
                    r.id,r.title_source,om.mention_text,
                    r.source_projection_json,r.normalized_projection_json,
                    r.normalized_content_hash,
                    ro.id,ro.content_type,ro.payload_sha256,ro.payload_text,
                    ro.parser_version,ro.transport_version
                from job_posting p
                join job_posting_revision r on r.id=p.current_revision_id
                left join organization_mention om on om.job_posting_revision_id=r.id
                join raw_observation ro on ro.id=r.raw_observation_id
                where p.id=%s
                """,
                (posting_id,),
            ).fetchone()
            if not row:
                raise RuntimeError(f"posting snapshot missing: {posting_id}")
            payload=row[13]
            actual=_sha256_text(payload)
            if actual!=row[12]:
                raise RuntimeError(f"payload sha mismatch before freeze: posting {posting_id}")
            record={
                "snapshot_version":"er-eval-02-freeze-v1",
                "posting_id":row[0],
                "source":row[1],
                "source_posting_id":row[2],
                "url":row[3],
                "revision_id":row[4],
                "title":row[5],
                "company_mention":row[6],
                "source_projection":row[7],
                "normalized_projection":row[8],
                "normalized_content_hash":row[9],
                "raw_observation_id":row[10],
                "content_type":row[11],
                "payload_sha256":row[12],
                "payload_text":payload,
                "parser_version":row[14],
                "transport_version":row[15],
            }
            key=f"{row[1]}__{row[2]}"
            path=postings_dir/f"{key}.json"
            encoded=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
            path.write_text(encoded,encoding="utf-8")
            postings[posting_id]={
                "key":key,
                "file":str(path.relative_to(out_dir)),
                "file_sha256":_sha256_text(encoded),
                "payload_sha256":row[12],
                "source":row[1],
                "source_posting_id":row[2],
            }

    pair_records=[]
    for r in pairs:
        pair_records.append({
            "pair_id":r[0],
            "a":postings[r[1]],
            "b":postings[r[2]],
            "stratum":r[3],
            "features":r[4],
            "candidate_evidence":r[5],
            "label":r[6],
            "basis":r[7],
            "rationale":r[8],
            "decision_evidence":r[9],
        })
    pairs_path=out_dir/"pairs.jsonl"
    pairs_text="\n".join(json.dumps(x,ensure_ascii=False,sort_keys=True) for x in pair_records)+"\n"
    pairs_path.write_text(pairs_text,encoding="utf-8")

    labels={}
    for x in pair_records:
        labels[x["label"]]=labels.get(x["label"],0)+1
    manifest={
        "snapshot_version":"er-eval-02-freeze-v1",
        "postings_count":len(postings),
        "pairs_count":len(pair_records),
        "labels":labels,
        "postings":sorted(postings.values(),key=lambda x:(x["source"],x["source_posting_id"])),
        "pairs_file":"pairs.jsonl",
        "pairs_file_sha256":_sha256_text(pairs_text),
    }
    manifest_text=json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    (out_dir/"manifest.json").write_text(manifest_text,encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--out",default="reports/er-eval-02-snapshot")
    args=p.parse_args()
    if not args.dsn: raise SystemExit("DATABASE_URL/--dsn required")
    result=freeze(args.dsn,Path(args.out))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
