from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected-postings", type=int, default=100)
    parser.add_argument("--report", default="reports/org-02-er-eval-verification.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    failures = []
    with psycopg.connect(args.dsn) as conn:
        def scalar(sql):
            return conn.execute(sql).fetchone()[0]
        summary = {
            "postings": scalar("select count(*) from job_posting"),
            "organization_mentions": scalar("select count(*) from organization_mention"),
            "organization_evidence": scalar("select count(*) from organization_evidence"),
            "domain_candidates": scalar("select count(*) from organization_domain_candidate"),
            "er_eval_pairs": scalar("select count(*) from er_eval_pair"),
            "auto_same": scalar("select count(*) from er_eval_pair where proposed_label='SAME_OPPORTUNITY' and label_basis='AUTO_DECISIVE'"),
            "auto_distinct": scalar("select count(*) from er_eval_pair where proposed_label='DISTINCT_OPPORTUNITY' and label_basis='AUTO_COUNTER'"),
            "unresolved": scalar("select count(*) from er_eval_pair where proposed_label='UNRESOLVED'"),
            "bad_pair_order": scalar("select count(*) from er_eval_pair where posting_a_id>=posting_b_id"),
            "missing_org_provenance": scalar("select count(*) from organization_evidence where provenance_json='{}'::jsonb"),
            "missing_org_versions": scalar("select count(*) from organization_evidence where resolver_version is null or resolver_version=''"),
            "missing_eval_features": scalar("select count(*) from er_eval_pair where features_json='{}'::jsonb"),
        }
    if summary["postings"] != args.expected_postings:
        failures.append(f"postings: expected {args.expected_postings}, got {summary['postings']}")
    if summary["organization_mentions"] == 0:
        failures.append("organization_mentions: expected > 0")
    if summary["organization_evidence"] < summary["organization_mentions"]:
        failures.append("organization evidence does not cover every mention")
    if summary["er_eval_pairs"] == 0:
        failures.append("ER-EVAL produced no review pairs")
    for key in ("bad_pair_order","missing_org_provenance","missing_org_versions","missing_eval_features"):
        if summary[key] != 0:
            failures.append(f"{key}: expected 0, got {summary[key]}")

    result = {"pass": not failures, "failures": failures, "summary": summary}
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
