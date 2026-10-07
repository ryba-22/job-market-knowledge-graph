from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import time
import uuid

import httpx

from .expansion_sources import SOURCES
from .retry import RetryPolicy, run_with_retry
from .sources import ADAPTERS
from .storage import PostgresStore
from .versions import PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS


USER_AGENT = "job-market-knowledge-graph/SCALE-01 (+https://github.com/ryba-22/job-market-knowledge-graph)"


def load_known_ids(path: str, source: str) -> set[str]:
    raw = gzip.decompress(Path(path).read_bytes()).decode("utf-8")
    return {
        str(row["source_posting_id"])
        for line in raw.splitlines()
        if line
        for row in [json.loads(line)]
        if row["source"] == source
    }


def _discover_unknown(client, source: str, known: set[str], discovery_limit: int):
    if source == "pracuj":
        adapter = SOURCES[source]
        rows = adapter.discover_records(client, discovery_limit)
        return [row for row in rows if row[0].source_posting_id not in known], len(rows)
    if source == "justjoinit":
        refs = ADAPTERS[source].discover(client, discovery_limit)
    else:
        refs = SOURCES[source].discover(client, discovery_limit)
    return [ref for ref in refs if ref.source_posting_id not in known], len(refs)


def _retry_policy(source: str) -> RetryPolicy:
    if source == "bulldogjob":
        return RetryPolicy(max_attempts=4, base_delay_seconds=1.5)
    return RetryPolicy(max_attempts=3, base_delay_seconds=0.4)


def _record_success(
    store,
    *,
    run_id,
    source,
    ref,
    raw,
    final_url,
    status,
    content_type,
    parsed,
    attempt_no,
):
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
        run_id,
        source,
        parsed.source_posting_id,
        raw_observation_id=raw_id,
        job_posting_id=result["posting_id"],
    )
    return result


def collect(
    dsn: str,
    *,
    source: str,
    base_corpus: str,
    target: int,
    discovery_limit: int,
    delay: float,
    run_id: str,
):
    known = load_known_ids(base_corpus, source)
    store = PostgresStore(dsn)
    store.assert_migrated()
    store.begin_run(run_id, trigger_kind="scale-acquisition", source_scope=source)

    stats = Counter()
    errors = []
    manifest = []

    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
    ) as client:
        candidates, discovered_total = _discover_unknown(
            client, source, known, discovery_limit
        )

        for candidate in candidates:
            if stats["OBSERVED"] + stats["UNCHANGED"] + stats["CHANGED"] >= target:
                break

            if source == "pracuj":
                ref, item, requested_url = candidate
            else:
                ref = candidate
                item = None
                requested_url = ref.url

            if not store.claim_item(run_id, source, ref.source_posting_id):
                stats["REPLAY_SKIPPED"] += 1
                continue

            try:
                if source == "pracuj":
                    raw = json.dumps(item, ensure_ascii=False, sort_keys=True)
                    parsed = SOURCES[source].parse_detail(raw, ref)
                    result = _record_success(
                        store,
                        run_id=run_id,
                        source=source,
                        ref=ref,
                        raw=raw,
                        final_url=requested_url,
                        status=200,
                        content_type="application/json; transport=isitfair-public-search",
                        parsed=parsed,
                        attempt_no=1,
                    )
                    manifest_extra = {
                        "observation_provenance": "SECONDARY_PUBLIC_INDEX",
                        "mirror": "https://isitfair.pl",
                        "mirror_offer_uuid": item.get("offer_uuid"),
                    }
                else:
                    def fetch():
                        if source == "justjoinit":
                            response = client.get(ref.url)
                            response.raise_for_status()
                            return (
                                response.text,
                                str(response.url),
                                response.status_code,
                                response.headers.get("content-type", ""),
                            )
                        return SOURCES[source].fetch_detail(client, ref)

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
                        fetch,
                        policy=_retry_policy(source),
                        on_attempt_failure=on_failure,
                    )

                    if source == "justjoinit":
                        parsed = ADAPTERS[source].parse_detail(raw, final_url)
                    else:
                        parsed = SOURCES[source].parse_detail(raw, ref)

                    result = _record_success(
                        store,
                        run_id=run_id,
                        source=source,
                        ref=ref,
                        raw=raw,
                        final_url=final_url,
                        status=status,
                        content_type=content_type,
                        parsed=parsed,
                        attempt_no=attempt_no,
                    )
                    manifest_extra = {"observation_provenance": "DIRECT"}

                stats[result["state"]] += 1
                manifest.append(
                    {
                        "source": source,
                        "source_posting_id": parsed.source_posting_id,
                        "url": parsed.url,
                        **manifest_extra,
                    }
                )
            except Exception as exc:
                stats["ERROR"] += 1
                errors.append(
                    {
                        "source_posting_id": ref.source_posting_id,
                        "url": ref.url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                store.fail_item(run_id, source, ref.source_posting_id, str(exc))

            time.sleep(delay)

    successes = stats["OBSERVED"] + stats["UNCHANGED"] + stats["CHANGED"]
    report = {
        "run_id": run_id,
        "source": source,
        "base_known_ids": len(known),
        "discovery_limit": discovery_limit,
        "discovered_total": discovered_total,
        "unknown_candidates": len(candidates),
        "target_new": target,
        "successes": successes,
        "states": dict(stats),
        "errors": errors[:50],
        "transport": TRANSPORT_VERSIONS[source],
        "database": store.summary(),
    }
    if source == "pracuj":
        report.update(
            {
                "direct_source_access": False,
                "upstream_source": "pracuj.pl",
                "observation_provenance": "SECONDARY_PUBLIC_INDEX",
            }
        )

    status = "COMPLETED" if successes >= target and not errors else "PARTIAL"
    store.finish_run(run_id, status=status, summary=report)
    return report, manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument(
        "--source",
        required=True,
        choices=["justjoinit", "nofluffjobs", "rocketjobs", "bulldogjob", "pracuj"],
    )
    p.add_argument("--base-corpus", default="data/corpora/corpus-05/corpus.jsonl.gz")
    p.add_argument("--target", type=int, required=True)
    p.add_argument("--discovery-limit", type=int, required=True)
    p.add_argument("--delay", type=float, default=0.1)
    p.add_argument("--run-id")
    p.add_argument("--report", required=True)
    p.add_argument("--manifest", required=True)
    args = p.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    run_id = args.run_id or f"scale-01-{args.source}-{uuid.uuid4()}"
    report, manifest = collect(
        args.dsn,
        source=args.source,
        base_corpus=args.base_corpus,
        target=args.target,
        discovery_limit=args.discovery_limit,
        delay=args.delay,
        run_id=run_id,
    )

    rp = Path(args.report)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mp = Path(args.manifest)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(
        json.dumps({"source": args.source, "rows": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
