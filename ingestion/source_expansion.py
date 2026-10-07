from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time
import uuid

import httpx

from .expansion_sources import SOURCES
from .retry import RetryPolicy, run_with_retry
from .storage import PostgresStore
from .versions import PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS


USER_AGENT = "job-market-knowledge-graph/SOURCE-EXPANSION-01 (+https://github.com/ryba-22/job-market-knowledge-graph)"


def run_source(client, store, run_id: str, source: str, limit: int, delay: float):
    adapter = SOURCES[source]
    refs = adapter.discover(client, limit)
    stats = Counter()
    errors = []
    manifest = []
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25)

    for ref in refs:
        if not store.claim_item(run_id, source, ref.source_posting_id):
            stats["REPLAY_SKIPPED"] += 1
            manifest.append({"source": source, "source_posting_id": ref.source_posting_id, "url": ref.url})
            continue
        try:
            def fetch():
                return adapter.fetch_detail(client, ref)

            def on_failure(no, exc, will_retry, failure_type, status):
                store.record_attempt(
                    run_id=run_id,
                    source=source,
                    source_posting_id=ref.source_posting_id,
                    requested_url=ref.url,
                    attempt_no=no,
                    outcome="RETRYABLE_FAILURE" if will_retry else "TERMINAL_FAILURE",
                    failure_type=failure_type,
                    http_status=status,
                    error_message=str(exc),
                )

            (raw, final_url, status, content_type), attempt_no = run_with_retry(
                fetch, policy=policy, on_attempt_failure=on_failure
            )
            parsed = adapter.parse_detail(raw, ref)
            raw_id = store.record_fetch(
                source=source,
                url=ref.url,
                final_url=final_url,
                status=status,
                body=raw,
                content_type=content_type,
                run_id=run_id,
                source_posting_id=parsed.source_posting_id,
                parser_version=PARSER_BUNDLE_VERSION,
                transport_version=TRANSPORT_VERSIONS[source],
            )
            result = store.ingest(parsed, raw_id)
            store.record_attempt(
                run_id=run_id,
                source=source,
                source_posting_id=parsed.source_posting_id,
                requested_url=ref.url,
                attempt_no=attempt_no,
                outcome="SUCCESS",
                http_status=status,
            )
            store.complete_item(
                run_id, source, parsed.source_posting_id,
                raw_observation_id=raw_id,
                job_posting_id=result["posting_id"],
            )
            stats[result["state"]] += 1
            manifest.append({"source": source, "source_posting_id": parsed.source_posting_id, "url": parsed.url})
        except Exception as exc:
            stats["ERROR"] += 1
            errors.append({
                "source_posting_id": ref.source_posting_id,
                "url": ref.url,
                "error": f"{type(exc).__name__}: {exc}",
            })
            store.fail_item(run_id, source, ref.source_posting_id, str(exc))
        time.sleep(delay)

    return {
        "source": source,
        "transport": TRANSPORT_VERSIONS[source],
        "discovered": len(refs),
        "states": dict(stats),
        "errors": errors[:25],
    }, manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--source", choices=["nofluffjobs", "rocketjobs", "both"], default="both")
    p.add_argument("--limit-per-source", type=int, default=100)
    p.add_argument("--delay", type=float, default=0.1)
    p.add_argument("--run-id")
    p.add_argument("--manifest-out", default="reports/source-expansion-01-manifest.json")
    p.add_argument("--report", default="reports/source-expansion-01.json")
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    run_id = args.run_id or str(uuid.uuid4())
    sources = ["nofluffjobs", "rocketjobs"] if args.source == "both" else [args.source]
    store = PostgresStore(args.dsn)
    store.assert_migrated()
    store.begin_run(run_id, trigger_kind="source-expansion", source_scope=args.source)
    report = {"run_id": run_id, "sources": []}
    manifest = {"sources": {}}

    with httpx.Client(
        timeout=40,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
    ) as client:
        for source in sources:
            source_report, rows = run_source(client, store, run_id, source, args.limit_per_source, args.delay)
            report["sources"].append(source_report)
            manifest["sources"][source] = rows

    report["new_match_candidates"] = store.generate_match_candidates()
    report["database"] = store.summary()
    total_errors = sum(len(x["errors"]) for x in report["sources"])
    store.finish_run(run_id, status="PARTIAL" if total_errors else "COMPLETED", summary=report)

    rp = Path(args.report)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mp = Path(args.manifest_out)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
