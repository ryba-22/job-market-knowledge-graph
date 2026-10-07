from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg


ADJUDICATOR_VERSION="er-adjudicator-v1"


def _current_decision(conn,pair_id):
    return conn.execute(
        """
        select id,label,basis
        from er_adjudication_decision
        where er_eval_pair_id=%s
        order by created_at desc,id desc
        limit 1
        """,
        (pair_id,),
    ).fetchone()


def _evidence(conn,pair_id):
    rows=conn.execute(
        """
        select posting_id,evidence_type,direction,strength,value_json,provenance_json
        from opportunity_evidence
        where er_eval_pair_id=%s
        order by posting_id,id
        """,
        (pair_id,),
    ).fetchall()
    out=[]
    for r in rows:
        out.append({
            "posting_id":r[0],"type":r[1],"direction":r[2],"strength":r[3],
            "value":r[4],"provenance":r[5],
        })
    return out


def _same_ats(evidence):
    by_post={}
    for e in evidence:
        if e["type"]!="ATS_URL":
            continue
        ats=e["value"].get("ats") or {}
        ident=(ats.get("host"),ats.get("requisition"))
        if all(ident):
            by_post.setdefault(e["posting_id"],set()).add(ident)
    if len(by_post)<2:
        return None
    sets=list(by_post.values())
    shared=set.intersection(*sets)
    return sorted(shared)[0] if shared else None


def _same_application_url(evidence):
    by_post={}
    for e in evidence:
        if e["type"] not in ("APPLICATION_URL","ATS_URL"):
            continue
        url=e["value"].get("url")
        if url:
            by_post.setdefault(e["posting_id"],set()).add(url.rstrip("/"))
    if len(by_post)<2:
        return None
    shared=set.intersection(*list(by_post.values()))
    return sorted(shared)[0] if shared else None


def _different_explicit_requisitions(evidence):
    by_post={}
    for e in evidence:
        if e["type"]=="EXPLICIT_REQUISITION":
            val=e["value"].get("value")
            if val:
                by_post.setdefault(e["posting_id"],set()).add(str(val))
        elif e["type"]=="ATS_URL":
            ats=e["value"].get("ats") or {}
            if ats.get("host") and ats.get("requisition"):
                by_post.setdefault(e["posting_id"],set()).add(f"{ats['host']}::{ats['requisition']}")
    if len(by_post)<2:
        return None
    sets=list(by_post.values())
    if all(sets) and set.intersection(*sets):
        return None
    if all(sets):
        return {str(k):sorted(v) for k,v in by_post.items()}
    return None


def adjudicate(dsn: str) -> dict:
    counts=Counter()
    decisions=[]
    with psycopg.connect(dsn) as conn:
        pairs=conn.execute(
            "select id from er_eval_pair where review_status='PENDING' order by id"
        ).fetchall()
        for (pair_id,) in pairs:
            evidence=_evidence(conn,pair_id)
            shared_ats=_same_ats(evidence)
            shared_url=_same_application_url(evidence)
            distinct_reqs=_different_explicit_requisitions(evidence)
            if shared_ats:
                label="SAME_OPPORTUNITY"; basis="AUTO_DECISIVE"
                rationale=f"shared ATS requisition: {shared_ats[0]}::{shared_ats[1]}"
            elif shared_url:
                label="SAME_OPPORTUNITY"; basis="AUTO_DECISIVE"
                rationale=f"shared explicit external application target: {shared_url}"
            elif distinct_reqs:
                label="DISTINCT_OPPORTUNITY"; basis="AUTO_COUNTER"
                rationale="explicit requisition/application identities are distinct on both postings"
            else:
                label="UNRESOLVED"; basis="INSUFFICIENT_EVIDENCE"
                rationale="no shared decisive application/ATS identity and no decisive counter-evidence"
            prior=_current_decision(conn,pair_id)
            row=conn.execute(
                """
                insert into er_adjudication_decision(
                    er_eval_pair_id,label,basis,rationale,evidence_snapshot_json,
                    adjudicator_version,supersedes_decision_id
                )
                values (%s,%s,%s,%s,%s::jsonb,%s,%s)
                returning id
                """,
                (
                    pair_id,label,basis,rationale,
                    json.dumps(evidence,ensure_ascii=False),
                    ADJUDICATOR_VERSION,prior[0] if prior else None,
                ),
            ).fetchone()
            conn.execute(
                """
                update er_eval_pair
                set proposed_label=%s,
                    label_basis=%s,
                    review_status='REVIEWED'
                where id=%s
                """,
                (
                    label,
                    "AUTO_DECISIVE" if basis=="AUTO_DECISIVE"
                    else "AUTO_COUNTER" if basis=="AUTO_COUNTER"
                    else "PENDING",
                    pair_id,
                ),
            )
            counts[label]+=1
            decisions.append({"pair_id":pair_id,"decision_id":row[0],"label":label,"basis":basis,"rationale":rationale})
        conn.commit()
    return {"adjudicator_version":ADJUDICATOR_VERSION,"counts":dict(counts),"decisions":decisions}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--report",default="reports/er-eval-02-adjudication.json")
    args=p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    result=adjudicate(args.dsn)
    path=Path(args.report); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
