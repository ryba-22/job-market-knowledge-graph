from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected-per-source", type=int, default=50)
    parser.add_argument("--report", default="reports/crawl-03-verification.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    expected_total = args.expected_per_source * 2
    failures = []
    with psycopg.connect(args.dsn) as conn:
        def scalar(sql, params=()):
            return conn.execute(sql, params).fetchone()[0]

        by_source = dict(conn.execute(
            "select source_code, count(*) from job_posting group by source_code order by source_code"
        ).fetchall())
        lifecycle = dict(conn.execute(
            "select state, count(*) from posting_lifecycle_observation group by state order by state"
        ).fetchall())
        run_states = dict(conn.execute(
            "select status, count(*) from ingestion_run group by status order by status"
        ).fetchall())

        summary = {
            "migrations": scalar("select count(*) from schema_migration"),
            "postings": scalar("select count(*) from job_posting"),
            "revisions": scalar("select count(*) from job_posting_revision"),
            "raw_observations": scalar("select count(*) from raw_observation"),
            "lifecycle": lifecycle,
            "by_source": by_source,
            "ingestion_runs": scalar("select count(*) from ingestion_run"),
            "ingestion_items": scalar("select count(*) from ingestion_item"),
            "ingestion_attempts": scalar("select count(*) from ingestion_attempt"),
            "run_states": run_states,
            "missing_raw_versions": scalar(
                """
                select count(*) from raw_observation
                where parser_version is null or transport_version is null
                   or run_id is null or source_posting_id is null or archive_key is null
                """
            ),
            "missing_revision_versions": scalar(
                """
                select count(*) from job_posting_revision
                where parser_version is null or normalizer_version is null
                """
            ),
            "missing_org_resolver_versions": scalar(
                "select count(*) from organization_candidate where resolver_version is null"
            ),
            "missing_match_generator_versions": scalar(
                "select count(*) from match_candidate where candidate_generator_version is null"
            ),
        }

    for source in ("theprotocol", "justjoinit"):
        if by_source.get(source) != args.expected_per_source:
            failures.append(
                f"{source}: expected {args.expected_per_source} postings, got {by_source.get(source, 0)}"
            )
    expected = {
        "postings": expected_total,
        "revisions": expected_total,
        "raw_observations": expected_total * 2,
        "ingestion_runs": 2,
        "ingestion_items": expected_total * 2,
    }
    for key, value in expected.items():
        if summary[key] != value:
            failures.append(f"{key}: expected {value}, got {summary[key]}")
    if lifecycle.get("OBSERVED", 0) != expected_total:
        failures.append(f"OBSERVED: expected {expected_total}, got {lifecycle.get('OBSERVED', 0)}")
    if lifecycle.get("UNCHANGED", 0) != expected_total:
        failures.append(f"UNCHANGED: expected {expected_total}, got {lifecycle.get('UNCHANGED', 0)}")
    if lifecycle.get("CHANGED", 0) != 0:
        failures.append(f"CHANGED: expected 0, got {lifecycle.get('CHANGED', 0)}")
    if run_states.get("COMPLETED", 0) != 2:
        failures.append(f"completed runs: expected 2, got {run_states.get('COMPLETED', 0)}")
    for key in (
        "missing_raw_versions",
        "missing_revision_versions",
        "missing_org_resolver_versions",
        "missing_match_generator_versions",
    ):
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
