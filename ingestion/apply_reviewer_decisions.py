from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg


REVIEWER_VERSION="er-eval-02-review-v1"
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS=ROOT/"data"/"evals"/"er-eval-02-reviewer-decisions.json"


def _posting_id(conn, source: str, source_posting_id: str) -> int:
    row=conn.execute(
        "select id from job_posting where source_code=%s and source_posting_id=%s",
        (source,source_posting_id),
    ).fetchone()
    if not row:
        raise RuntimeError(f"posting not found: {source}:{source_posting_id}")
    return row[0]


def apply(dsn: str, path: Path=DEFAULT_DECISIONS) -> dict:
    payload=json.loads(path.read_text(encoding="utf-8"))
    applied=[]
    with psycopg.connect(dsn) as conn:
        for item in payload["decisions"]:
            a=_posting_id(conn,**item["a"])
            b=_posting_id(conn,**item["b"])
            x,y=sorted((a,b))
            pair=conn.execute(
                """
                select id from er_eval_pair
                where posting_a_id=%s and posting_b_id=%s
                order by id desc limit 1
                """,
                (x,y),
            ).fetchone()
            if not pair:
                raise RuntimeError(
                    f"review pair missing for {item['a']} vs {item['b']}"
                )
            pair_id=pair[0]
            prior=conn.execute(
                """
                select id from er_adjudication_decision
                where er_eval_pair_id=%s
                order by created_at desc,id desc limit 1
                """,
                (pair_id,),
            ).fetchone()
            evidence_snapshot={
                "reviewer_evidence":item.get("evidence",[]),
                "source_pair":{"a":item["a"],"b":item["b"]},
            }
            decision=conn.execute(
                """
                insert into er_adjudication_decision(
                    er_eval_pair_id,label,basis,rationale,evidence_snapshot_json,
                    adjudicator_version,supersedes_decision_id
                )
                values (%s,%s,'REVIEWER',%s,%s::jsonb,%s,%s)
                returning id
                """,
                (
                    pair_id,item["label"],item["rationale"],
                    json.dumps(evidence_snapshot,ensure_ascii=False),
                    REVIEWER_VERSION,prior[0] if prior else None,
                ),
            ).fetchone()[0]
            conn.execute(
                """
                update er_eval_pair
                set proposed_label=%s,label_basis='HUMAN',review_status='REVIEWED'
                where id=%s
                """,
                (item["label"],pair_id),
            )
            applied.append({
                "pair_id":pair_id,
                "decision_id":decision,
                "label":item["label"],
                "a":item["a"],
                "b":item["b"],
            })
        conn.commit()
    return {"reviewer_version":REVIEWER_VERSION,"applied_count":len(applied),"applied":applied}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--decisions",default=str(DEFAULT_DECISIONS))
    p.add_argument("--report",default="reports/er-eval-02-reviewer-decisions.json")
    args=p.parse_args()
    if not args.dsn: raise SystemExit("DATABASE_URL/--dsn required")
    result=apply(args.dsn,Path(args.decisions))
    out=Path(args.report); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
