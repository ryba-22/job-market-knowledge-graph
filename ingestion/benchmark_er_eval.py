from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg


def build(dsn: str) -> dict:
    with psycopg.connect(dsn) as conn:
        rows=conn.execute(
            """
            select e.id,d.label,d.basis,e.stratum
            from er_eval_pair e
            join lateral (
                select label,basis
                from er_adjudication_decision
                where er_eval_pair_id=e.id
                order by created_at desc,id desc limit 1
            ) d on true
            order by e.id
            """
        ).fetchall()
    labels={"SAME_OPPORTUNITY":0,"DISTINCT_OPPORTUNITY":0,"UNRESOLVED":0}
    bases={}
    for _,label,basis,_ in rows:
        labels[label]=labels.get(label,0)+1
        bases[basis]=bases.get(basis,0)+1
    resolved=labels["SAME_OPPORTUNITY"]+labels["DISTINCT_OPPORTUNITY"]
    auto_resolved=sum(1 for _,_,basis,_ in rows if basis in ("AUTO_DECISIVE","AUTO_COUNTER"))
    return {
        "pairs":len(rows),
        "labels":labels,
        "basis":bases,
        "resolved_pairs":resolved,
        "resolution_rate":round(resolved/len(rows),4) if rows else 0.0,
        "auto_resolved_pairs":auto_resolved,
        "precision_auto_link":None,
        "recall_at_candidate_set":None,
        "metric_notes":{
            "precision_auto_link":"undefined until at least one AUTO_DECISIVE link exists",
            "recall_at_candidate_set":"not measurable from candidate-only adjudication; requires labeled pairs outside candidate set or a known-positive reference set",
        },
        "calibration_ready":False,
        "calibration_blocker":"too few adjudicated SAME/DISTINCT labels; collect a broader labeled reference set before fitting weights or thresholds",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--report",default="reports/er-eval-02-benchmark.json")
    args=p.parse_args()
    if not args.dsn: raise SystemExit("DATABASE_URL/--dsn required")
    result=build(args.dsn)
    out=Path(args.report); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
