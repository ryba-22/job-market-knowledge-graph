from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time
import uuid

import httpx

from .retry import RetryPolicy, run_with_retry
from .sources import ADAPTERS
from .storage import PostgresStore
from .theprotocol_mcp import fetch_batch_sync, fetch_groups_sync, parse as parse_theprotocol
from .versions import PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS


USER_AGENT = "job-market-knowledge-graph/CRAWL-03 (+https://github.com/ryba-22/job-market-knowledge-graph)"


def _load_manifest(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    return json.loads(p.read_text(encoding="utf-8"))


def run_theprotocol(
    store: PostgresStore,
    run_id: str,
    limit: int,
    manifest_rows: list[dict] | None = None,
) -> tuple[dict, list[dict]]:
    stats = Counter()
    errors = []
    changes = []
    manifest = []

    if manifest_rows:
        claimed = []
        for row in manifest_rows:
            sid = row["source_posting_id"]
            if store.claim_item(run_id, "theprotocol", sid):
                claimed.append(row)
            else:
                stats["REPLAY_SKIPPED"] += 1
                manifest.append(row)
        search_rows = [row["search"] for row in claimed]
        gids = [str(row["groupId"]) for row in claimed]
        details_rows = fetch_groups_sync(gids) if gids else []
        pairs = list(zip(search_rows, details_rows))
    else:
        pairs = fetch_batch_sync(limit)

    for search_row, details in pairs:
        sid_hint = str(search_row.get("offerId") or search_row.get("groupId") or "")
        try:
            parsed = parse_theprotocol(search_row, details)
            sid = parsed.source_posting_id
            if not manifest_rows and not store.claim_item(run_id, "theprotocol", sid):
                stats["REPLAY_SKIPPED"] += 1
                continue
            raw_text = json.dumps(
                {"search": search_row, "details": details},
                ensure_ascii=False,
                sort_keys=True,
            )
            target = parsed.url or f"mcp://theprotocol/{sid}"
            raw_id = store.record_fetch(
                source="theprotocol",
                url=target,
                final_url=target,
                status=200,
                body=raw_text,
                content_type="application/json; transport=official-mcp",
                run_id=run_id,
                source_posting_id=sid,
                parser_version=PARSER_BUNDLE_VERSION,
                transport_version=TRANSPORT_VERSIONS["theprotocol"],
            )
            result = store.ingest(parsed, raw_id)
            store.record_attempt(
                run_id=run_id,
                source="theprotocol",
                source_posting_id=sid,
                requested_url=target,
                attempt_no=1,
                outcome="SUCCESS",
                http_status=200,
            )
            store.complete_item(
                run_id,
                "theprotocol",
                sid,
                raw_observation_id=raw_id,
                job_posting_id=result["posting_id"],
            )
            stats[result["state"]] += 1
            if result["state"] == "CHANGED":
                changes.append({
                    "source_posting_id": sid,
                    "changed_fields": result.get("changed_fields", []),
                    "change_preview": result.get("change_preview", {}),
                })
            manifest.append({
                "source": "theprotocol",
                "source_posting_id": sid,
                "groupId": parsed.source_specific.get("groupId"),
                "url": parsed.url,
                "search": search_row,
            })
        except Exception as exc:
            sid = sid_hint or "unknown"
            stats["ERROR"] += 1
            errors.append({"id": sid, "error": f"{type(exc).__name__}: {exc}"})
            if sid != "unknown":
                store.record_attempt(
                    run_id=run_id,
                    source="theprotocol",
                    source_posting_id=sid,
                    requested_url=f"mcp://theprotocol/{sid}",
                    attempt_no=1,
                    outcome="TERMINAL_FAILURE",
                    failure_type=type(exc).__name__,
                    error_message=str(exc),
                )
                store.fail_item(run_id, "theprotocol", sid, str(exc))

    return ({
        "source": "theprotocol",
        "transport": TRANSPORT_VERSIONS["theprotocol"],
        "discovered": len(pairs) + stats["REPLAY_SKIPPED"],
        "states": dict(stats),
        "changes": changes[:25],
        "errors": errors[:20],
    }, manifest)


def run_jjit(
    client: httpx.Client,
    store: PostgresStore,
    run_id: str,
    limit: int,
    delay: float,
    manifest_rows: list[dict] | None = None,
) -> tuple[dict, list[dict]]:
    adapter = ADAPTERS["justjoinit"]
    if manifest_rows:
        from .model import PostingRef
        refs = [PostingRef("justjoinit", row["url"], row["source_posting_id"]) for row in manifest_rows]
    else:
        refs = adapter.discover(client, limit)

    stats = Counter()
    errors = []
    changes = []
    manifest = []
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25)

    for ref in refs:
        if not store.claim_item(run_id, "justjoinit", ref.source_posting_id):
            stats["REPLAY_SKIPPED"] += 1
            manifest.append({
                "source": "justjoinit",
                "source_posting_id": ref.source_posting_id,
                "url": ref.url,
            })
            continue

        attempt_no = 1
        try:
            def fetch():
                response = client.get(ref.url)
                response.raise_for_status()
                return response

            def on_failure(no, exc, will_retry, failure_type, status):
                store.record_attempt(
                    run_id=run_id,
                    source="justjoinit",
                    source_posting_id=ref.source_posting_id,
                    requested_url=ref.url,
                    attempt_no=no,
                    outcome="RETRYABLE_FAILURE" if will_retry else "TERMINAL_FAILURE",
                    failure_type=failure_type,
                    http_status=status,
                    error_message=str(exc),
                )

            response, attempt_no = run_with_retry(fetch, policy=policy, on_attempt_failure=on_failure)
            raw_id = store.record_fetch(
                source="justjoinit",
                url=ref.url,
                final_url=str(response.url),
                status=response.status_code,
                body=response.text,
                content_type=response.headers.get("content-type"),
                run_id=run_id,
                source_posting_id=ref.source_posting_id,
                parser_version=PARSER_BUNDLE_VERSION,
                transport_version=TRANSPORT_VERSIONS["justjoinit"],
            )
            parsed = adapter.parse_detail(response.text, str(response.url))
            result = store.ingest(parsed, raw_id)
            store.record_attempt(
                run_id=run_id,
                source="justjoinit",
                source_posting_id=ref.source_posting_id,
                requested_url=ref.url,
                attempt_no=attempt_no,
                outcome="SUCCESS",
                http_status=response.status_code,
            )
            store.complete_item(
                run_id,
                "justjoinit",
                ref.source_posting_id,
                raw_observation_id=raw_id,
                job_posting_id=result["posting_id"],
            )
            stats[result["state"]] += 1
            if result["state"] == "CHANGED":
                changes.append({
                    "source_posting_id": parsed.source_posting_id,
                    "changed_fields": result.get("changed_fields", []),
                    "change_preview": result.get("change_preview", {}),
                })
            manifest.append({
                "source": "justjoinit",
                "source_posting_id": parsed.source_posting_id,
                "url": parsed.url,
            })
        except Exception as exc:
            stats["ERROR"] += 1
            errors.append({"url": ref.url, "error": f"{type(exc).__name__}: {exc}"})
            store.fail_item(run_id, "justjoinit", ref.source_posting_id, str(exc))
        time.sleep(delay)

    return ({
        "source": "justjoinit",
        "transport": TRANSPORT_VERSIONS["justjoinit"],
        "discovered": len(refs),
        "states": dict(stats),
        "changes": changes[:25],
        "errors": errors[:20],
    }, manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--trigger-kind", default="manual")
    parser.add_argument("--source", choices=["theprotocol", "justjoinit", "both"], default="both")
    parser.add_argument("--limit-per-source", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.20)
    parser.add_argument("--manifest-in")
    parser.add_argument("--manifest-out")
    parser.add_argument("--report", default="reports/crawl-03-run.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    run_id = args.run_id or str(uuid.uuid4())
    existing_manifest = _load_manifest(args.manifest_in)
    store = PostgresStore(args.dsn)
    store.assert_migrated()
    store.begin_run(run_id, trigger_kind=args.trigger_kind, source_scope=args.source)
    report = {"run_id": run_id, "sources": []}
    manifest = {"sources": {}}

    try:
        with httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
        ) as client:
            if args.source in ("theprotocol", "both"):
                source_report, rows = run_theprotocol(
                    store,
                    run_id,
                    args.limit_per_source,
                    existing_manifest.get("sources", {}).get("theprotocol"),
                )
                report["sources"].append(source_report)
                manifest["sources"]["theprotocol"] = rows

            if args.source in ("justjoinit", "both"):
                source_report, rows = run_jjit(
                    client,
                    store,
                    run_id,
                    args.limit_per_source,
                    args.delay,
                    existing_manifest.get("sources", {}).get("justjoinit"),
                )
                report["sources"].append(source_report)
                manifest["sources"]["justjoinit"] = rows

        report["new_match_candidates"] = store.generate_match_candidates()
        report["database"] = store.summary()
        total_errors = sum(len(s.get("errors", [])) for s in report["sources"])
        store.finish_run(
            run_id,
            status="PARTIAL" if total_errors else "COMPLETED",
            summary=report,
        )
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        store.finish_run(run_id, status="FAILED", summary=report)
        raise

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.manifest_out:
        mp = Path(args.manifest_out)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
