from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import psycopg


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--report",default="reports/er-eval-02-verification.json")
    args=p.parse_args()
    if not args.dsn: raise SystemExit("DATABASE_URL/--dsn required")
    failures=[]
    with psycopg.connect(args.dsn) as conn:
        def q(sql): return conn.execute(sql).fetchone()[0]
        summary={
            "pairs":q("select count(*) from er_eval_pair"),
            "reviewed":q("select count(*) from er_eval_pair where review_status='REVIEWED'"),
            "decisions":q("select count(*) from er_adjudication_decision"),
            "same":q("select count(*) from er_adjudication_decision d where d.id in (select max(id) from er_adjudication_decision group by er_eval_pair_id) and d.label='SAME_OPPORTUNITY'"),
            "distinct":q("select count(*) from er_adjudication_decision d where d.id in (select max(id) from er_adjudication_decision group by er_eval_pair_id) and d.label='DISTINCT_OPPORTUNITY'"),
            "unresolved":q("select count(*) from er_adjudication_decision d where d.id in (select max(id) from er_adjudication_decision group by er_eval_pair_id) and d.label='UNRESOLVED'"),
            "portal_domain_contamination":q("select count(*) from organization_domain_candidate where domain='justjoin.it' or domain like '%.justjoin.it' or domain='theprotocol.it' or domain like '%.theprotocol.it'"),
            "missing_evidence_provenance":q("select count(*) from opportunity_evidence where provenance_json='{}'::jsonb"),
            "bad_auto_same":q("select count(*) from er_adjudication_decision where label='SAME_OPPORTUNITY' and basis not in ('AUTO_DECISIVE','REVIEWER')"),
            "reviewer_same":q("select count(*) from er_adjudication_decision d where d.id in (select max(id) from er_adjudication_decision group by er_eval_pair_id) and d.label='SAME_OPPORTUNITY' and d.basis='REVIEWER'"),
            "reviewer_distinct":q("select count(*) from er_adjudication_decision d where d.id in (select max(id) from er_adjudication_decision group by er_eval_pair_id) and d.label='DISTINCT_OPPORTUNITY' and d.basis='REVIEWER'"),
        }
    if summary["pairs"]==0: failures.append("no evaluation pairs")
    if summary["reviewed"]!=summary["pairs"]: failures.append(f"reviewed {summary['reviewed']} != pairs {summary['pairs']}")
    if summary["decisions"]<summary["pairs"]: failures.append("missing adjudication decisions")
    for key in ("portal_domain_contamination","missing_evidence_provenance","bad_auto_same"):
        if summary[key]!=0: failures.append(f"{key}: expected 0 got {summary[key]}")
    if summary["reviewer_same"] < 1:
        failures.append("expected at least one reviewer SAME decision")
    if summary["reviewer_distinct"] < 1:
        failures.append("expected at least one reviewer DISTINCT decision")
    result={"pass":not failures,"failures":failures,"summary":summary}
    path=Path(args.report); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if failures: raise SystemExit(1)


if __name__=="__main__":
    main()
