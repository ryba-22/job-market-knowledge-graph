from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

import httpx

from .expansion_sources import SOURCES
from .model import PostingRef, SourceGoneError
from .retry import RetryPolicy, run_with_retry
from .sources import ADAPTERS
from .storage import PostgresStore
from .versions import PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS

USER_AGENT = "job-market-knowledge-graph/SCALE-02-chunk-worker"


def _load_chunk(path: str, source: str, chunk_index: int):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    for chunk in plan["chunks"]:
        if chunk["source"] == source and int(chunk["chunk_index"]) == chunk_index:
            return chunk
    raise KeyError(f"chunk not found: {source}:{chunk_index}")


def _retry_policy(source: str) -> RetryPolicy:
    if source == "bulldogjob":
        return RetryPolicy(max_attempts=4, base_delay_seconds=1.5)
    return RetryPolicy(max_attempts=3, base_delay_seconds=0.4)


def process(dsn: str, *, plan_path: str, source: str, chunk_index: int, delay: float, run_id: str):
    chunk = _load_chunk(plan_path, source, chunk_index)
    store = PostgresStore(dsn)
    store.assert_migrated()
    store.begin_run(run_id, trigger_kind="scale-02-chunk", source_scope=source)
    stats = Counter()
    errors = []
    manifest = []
    policy = _retry_policy(source)

    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
    ) as client:
        for row in chunk["rows"]:
            ref = PostingRef(source, row["url"], str(row["source_posting_id"]))
            sid = ref.source_posting_id
            if not store.claim_item(run_id, source, sid):
                stats["REPLAY_SKIPPED"] += 1
                continue
            try:
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
                    gone = status in (404, 410)
                    store.record_attempt(
                        run_id=run_id,
                        source=source,
                        source_posting_id=sid,
                        requested_url=ref.url,
                        attempt_no=no,
                        outcome="SOURCE_GONE" if gone else ("RETRYABLE_FAILURE" if will_retry else "TERMINAL_FAILURE"),
                        failure_type=failure_type,
                        http_status=status,
                        error_message=str(exc),
                    )

                (raw, final_url, status, content_type), attempt_no = run_with_retry(
                    fetch,
                    policy=policy,
                    on_attempt_failure=on_failure,
                )
                raw_id = store.record_fetch(
                    source=source,
                    url=ref.url,
                    final_url=final_url,
                    status=status,
                    body=raw,
                    content_type=content_type,
                    run_id=run_id,
                    source_posting_id=sid,
                    parser_version=PARSER_BUNDLE_VERSION,
                    transport_version=TRANSPORT_VERSIONS[source],
                )
                parsed = (
                    ADAPTERS[source].parse_detail(raw, final_url)
                    if source == "justjoinit"
                    else SOURCES[source].parse_detail(raw, ref)
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
                stats[result["state"]] += 1
                manifest.append({
                    "source": source,
                    "source_posting_id": parsed.source_posting_id,
                    "url": parsed.url,
                    "observation_provenance": "DIRECT",
                })
            except Exception as exc:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                if isinstance(exc, SourceGoneError) or status in (404, 410):
                    stats["SOURCE_GONE"] += 1
                    store.source_gone_item(run_id, source, sid, str(exc))
                else:
                    stats["ERROR"] += 1
                    errors.append({
                        "source_posting_id": sid,
                        "url": ref.url,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    store.fail_item(run_id, source, sid, str(exc))
            time.sleep(delay)

    successes = stats["OBSERVED"] + stats["UNCHANGED"] + stats["CHANGED"]
    source_gone = stats["SOURCE_GONE"]
    report = {
        "run_id": run_id,
        "source": source,
        "chunk_index": chunk_index,
        "planned": chunk["count"],
        "successes": successes,
        "source_gone": source_gone,
        "states": dict(stats),
        "errors": errors[:100],
        "transport": TRANSPORT_VERSIONS[source],
        "first_source_posting_id": chunk["first_source_posting_id"],
        "last_source_posting_id": chunk["last_source_posting_id"],
        "database": store.summary(),
    }
    store.finish_run(
        run_id,
        status="COMPLETED" if successes + source_gone == chunk["count"] and not errors else "PARTIAL",
        summary=report,
    )
    return report, manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--plan", default="data/inventories/scale-02/chunks.json")
    p.add_argument("--source", required=True, choices=("justjoinit", "nofluffjobs", "rocketjobs", "bulldogjob", "solidjobs", "teamquest"))
    p.add_argument("--chunk-index", required=True, type=int)
    p.add_argument("--delay", type=float, default=0.1)
    p.add_argument("--run-id")
    p.add_argument("--report", required=True)
    p.add_argument("--manifest", required=True)
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    run_id = args.run_id or f"scale-02-{args.source}-{args.chunk_index}"
    report, manifest = process(
        args.dsn,
        plan_path=args.plan,
        source=args.source,
        chunk_index=args.chunk_index,
        delay=args.delay,
        run_id=run_id,
    )
    rp = Path(args.report)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mp = Path(args.manifest)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(
        json.dumps({"source": args.source, "chunk_index": args.chunk_index, "rows": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
