from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import psycopg


def export(dsn: str, jsonl_path: str, csv_path: str):
    with psycopg.connect(dsn) as conn:
        rows=conn.execute(
            """
            select
                e.id,e.stratum,e.features_json,
                pa.source_code,pa.source_posting_id,pa.canonical_source_url,
                pb.source_code,pb.source_posting_id,pb.canonical_source_url,
                d.label,d.basis,d.rationale,d.evidence_snapshot_json
            from er_eval_pair e
            join job_posting pa on pa.id=e.posting_a_id
            join job_posting pb on pb.id=e.posting_b_id
            left join lateral (
                select label,basis,rationale,evidence_snapshot_json
                from er_adjudication_decision
                where er_eval_pair_id=e.id
                order by created_at desc,id desc limit 1
            ) d on true
            order by e.id
            """
        ).fetchall()
    records=[]
    for r in rows:
        records.append({
            "pair_id":r[0],"stratum":r[1],"features":r[2],
            "a":{"source":r[3],"source_posting_id":r[4],"url":r[5]},
            "b":{"source":r[6],"source_posting_id":r[7],"url":r[8]},
            "label":r[9],"basis":r[10],"rationale":r[11],"evidence":r[12],
        })
    jp=Path(jsonl_path); jp.parent.mkdir(parents=True,exist_ok=True)
    jp.write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in records)+("\n" if records else ""),encoding="utf-8")
    cp=Path(csv_path); cp.parent.mkdir(parents=True,exist_ok=True)
    with cp.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["pair_id","stratum","org_a","title_a","org_b","title_b","label","basis","rationale","url_a","url_b"])
        w.writeheader()
        for x in records:
            feat=x["features"]
            w.writerow({
                "pair_id":x["pair_id"],"stratum":x["stratum"],
                "org_a":feat.get("org_a"),"title_a":feat.get("title_a"),
                "org_b":feat.get("org_b"),"title_b":feat.get("title_b"),
                "label":x["label"],"basis":x["basis"],"rationale":x["rationale"],
                "url_a":x["a"]["url"],"url_b":x["b"]["url"],
            })
    return {"pairs":len(records),"jsonl":str(jp),"csv":str(cp)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--jsonl",default="reports/er-eval-02-final.jsonl")
    p.add_argument("--csv",default="reports/er-eval-02-final.csv")
    args=p.parse_args()
    if not args.dsn: raise SystemExit("DATABASE_URL/--dsn required")
    print(json.dumps(export(args.dsn,args.jsonl,args.csv),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
