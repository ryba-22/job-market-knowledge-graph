from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time
import httpx
from .model import PostingRef
from .retry import RetryPolicy, run_with_retry
from .sources import ADAPTERS, NFJ_SEARCH_URL
from .storage import PostgresStore
from .versions import PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS

USER_AGENT = "job-market-knowledge-graph/SOURCE-EXPANSION-01 (+https://github.com/ryba-22/job-market-knowledge-graph)"
ISITFAIR_SEARCH_URL = "https://isitfair.pl/api/v1/offers/search"
PRACUJ_SEARCH_TERMS = (
    "developer","engineer","programista","java","python","devops","data","tester",
    "analityk","administrator","cloud","security","frontend","backend","fullstack",
    "architect","ai","mlops","scrum","product","software","kubernetes","sql","automation",
)

def _success_count(stats: Counter) -> int:
    return stats["OBSERVED"] + stats["UNCHANGED"] + stats["CHANGED"]

def _record_success(store, *, run_id, source, sid, requested_url, response_url,
                    status, content_type, body, parsed, attempt_no):
    raw_id = store.record_fetch(
        source=source, url=requested_url, final_url=response_url, status=status,
        body=body, content_type=content_type, run_id=run_id,
        source_posting_id=sid, parser_version=PARSER_BUNDLE_VERSION,
        transport_version=TRANSPORT_VERSIONS[source],
    )
    result = store.ingest(parsed, raw_id)
    store.record_attempt(
        run_id=run_id, source=source, source_posting_id=sid,
        requested_url=requested_url, attempt_no=attempt_no,
        outcome="SUCCESS", http_status=status,
    )
    store.complete_item(
        run_id, source, sid, raw_observation_id=raw_id,
        job_posting_id=result["posting_id"],
    )
    return result

def _run_direct_html(client, store, run_id, source, target, delay):
    adapter = ADAPTERS[source]
    refs = adapter.discover(client, max(target + 25, 100))
    stats, errors, manifest = Counter(), [], []
    policy = RetryPolicy(
        max_attempts=4 if source == "bulldogjob" else 3,
        base_delay_seconds=1.5 if source == "bulldogjob" else 0.25,
    )
    for ref in refs:
        if _success_count(stats) >= target:
            break
        sid = ref.source_posting_id
        if not store.claim_item(run_id, source, sid):
            stats["REPLAY_SKIPPED"] += 1
            manifest.append({"source":source,"source_posting_id":sid,"url":ref.url})
            continue
        try:
            def fetch():
                response = client.get(ref.url)
                response.raise_for_status()
                return response
            def on_failure(no, exc, will_retry, failure_type, status):
                store.record_attempt(
                    run_id=run_id, source=source, source_posting_id=sid,
                    requested_url=ref.url, attempt_no=no,
                    outcome="RETRYABLE_FAILURE" if will_retry else "TERMINAL_FAILURE",
                    failure_type=failure_type, http_status=status, error_message=str(exc),
                )
            response, attempt_no = run_with_retry(fetch, policy=policy, on_attempt_failure=on_failure)
            parsed = adapter.parse_detail(response.text, str(response.url))
            result = _record_success(
                store, run_id=run_id, source=source, sid=parsed.source_posting_id,
                requested_url=ref.url, response_url=str(response.url),
                status=response.status_code, content_type=response.headers.get("content-type"),
                body=response.text, parsed=parsed, attempt_no=attempt_no,
            )
            stats[result["state"]] += 1
            manifest.append({
                "source":source,"source_posting_id":parsed.source_posting_id,
                "url":parsed.url,
                "observation_provenance":parsed.source_specific.get("observation_provenance"),
            })
        except Exception as exc:
            stats["ERROR"] += 1
            errors.append({"source_posting_id":sid,"url":ref.url,"error":f"{type(exc).__name__}: {exc}"})
            store.fail_item(run_id, source, sid, str(exc))
        time.sleep(delay)
    return ({
        "source":source,"transport":TRANSPORT_VERSIONS[source],
        "discovered":len(refs),"target":target,"successes":_success_count(stats),
        "states":dict(stats),"errors":errors[:25],
    }, manifest)

def _discover_nfj(client, limit):
    adapter = ADAPTERS["nofluffjobs"]
    response = client.post(
        NFJ_SEARCH_URL,
        params={
            "limit": max(limit, 100),
            "offset": 0,
            "salaryCurrency": "PLN",
            "salaryPeriod": "month",
            "region": "pl",
        },
        json={"page": 1, "criteriaSearch": {}},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    refs = adapter.parse_listing(response.text, str(response.url))
    return refs[:limit]

def _run_nfj(client, store, run_id, target, delay):
    source = "nofluffjobs"
    adapter = ADAPTERS[source]
    refs = _discover_nfj(client, max(target + 25, 100))
    stats, errors, manifest = Counter(), [], []
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25)
    for ref in refs:
        if _success_count(stats) >= target:
            break
        sid = ref.source_posting_id
        if not store.claim_item(run_id, source, sid):
            stats["REPLAY_SKIPPED"] += 1
            manifest.append({"source":source,"source_posting_id":sid,"url":ref.url})
            continue
        slug = ref.url.rstrip("/").split("/")[-1]
        api_url = f"https://nofluffjobs.com/api/posting/{slug}"
        try:
            def fetch():
                response = client.get(api_url, headers={"Accept":"application/json"})
                response.raise_for_status()
                return response
            def on_failure(no, exc, will_retry, failure_type, status):
                store.record_attempt(
                    run_id=run_id, source=source, source_posting_id=sid,
                    requested_url=api_url, attempt_no=no,
                    outcome="RETRYABLE_FAILURE" if will_retry else "TERMINAL_FAILURE",
                    failure_type=failure_type, http_status=status, error_message=str(exc),
                )
            response, attempt_no = run_with_retry(fetch, policy=policy, on_attempt_failure=on_failure)
            parsed = adapter.parse_detail(response.text, ref.url)
            result = _record_success(
                store, run_id=run_id, source=source, sid=parsed.source_posting_id,
                requested_url=api_url, response_url=str(response.url),
                status=response.status_code, content_type=response.headers.get("content-type"),
                body=response.text, parsed=parsed, attempt_no=attempt_no,
            )
            stats[result["state"]] += 1
            manifest.append({
                "source":source,"source_posting_id":parsed.source_posting_id,
                "url":parsed.url,"api_url":api_url,
                "observation_provenance":"DIRECT_PUBLIC_API",
            })
        except Exception as exc:
            stats["ERROR"] += 1
            errors.append({"source_posting_id":sid,"url":api_url,"error":f"{type(exc).__name__}: {exc}"})
            store.fail_item(run_id, source, sid, str(exc))
        time.sleep(delay)
    return ({
        "source":source,"transport":TRANSPORT_VERSIONS[source],
        "discovered":len(refs),"target":target,"successes":_success_count(stats),
        "states":dict(stats),"errors":errors[:25],
    }, manifest)

def _discover_pracuj_mirror(client, limit):
    adapter = ADAPTERS["pracuj"]
    found = {}
    for term in PRACUJ_SEARCH_TERMS:
        response = client.get(
            ISITFAIR_SEARCH_URL,
            params={"search":term,"offer_status":"active"},
            headers={"Accept":"application/json"},
        )
        response.raise_for_status()
        for item in response.json().get("data", []):
            if item.get("offer_source") != "pracuj.pl":
                continue
            refs = adapter.parse_listing(
                json.dumps({"data":[item]}, ensure_ascii=False), str(response.url)
            )
            if not refs:
                continue
            ref = refs[0]
            found.setdefault(ref.source_posting_id, (ref, item, str(response.url)))
            if len(found) >= limit:
                return list(found.values())[:limit]
    return list(found.values())[:limit]

def _run_pracuj_mirror(client, store, run_id, target):
    source = "pracuj"
    adapter = ADAPTERS[source]
    rows = _discover_pracuj_mirror(client, max(target + 25, 100))
    stats, errors, manifest = Counter(), [], []
    for ref, item, requested_url in rows:
        if _success_count(stats) >= target:
            break
        sid = ref.source_posting_id
        if not store.claim_item(run_id, source, sid):
            stats["REPLAY_SKIPPED"] += 1
            continue
        try:
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True)
            parsed = adapter.parse_detail(raw, ref.url)
            result = _record_success(
                store, run_id=run_id, source=source, sid=sid,
                requested_url=requested_url, response_url=requested_url,
                status=200, content_type="application/json; transport=isitfair-public-search",
                body=raw, parsed=parsed, attempt_no=1,
            )
            stats[result["state"]] += 1
            manifest.append({
                "source":source,"source_posting_id":sid,"url":parsed.url,
                "mirror":"https://isitfair.pl","mirror_offer_uuid":item.get("offer_uuid"),
                "observation_provenance":"SECONDARY_PUBLIC_INDEX",
            })
        except Exception as exc:
            stats["ERROR"] += 1
            errors.append({"source_posting_id":sid,"url":ref.url,"error":f"{type(exc).__name__}: {exc}"})
            store.fail_item(run_id, source, sid, str(exc))
    return ({
        "source":source,"transport":TRANSPORT_VERSIONS[source],
        "direct_source_access":False,"upstream_source":"pracuj.pl",
        "mirror":"isitfair.pl public search","discovered":len(rows),
        "target":target,"successes":_success_count(stats),
        "states":dict(stats),"errors":errors[:25],
    }, manifest)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--target-per-source", type=int, default=75)
    p.add_argument("--delay", type=float, default=0.08)
    p.add_argument("--report", default="reports/source-expansion-01-run.json")
    p.add_argument("--manifest", default="reports/source-expansion-01-manifest.json")
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    store = PostgresStore(args.dsn)
    store.assert_migrated()
    run_id = "source-expansion-01"
    store.begin_run(
        run_id, trigger_kind="source-expansion",
        source_scope="nofluffjobs,rocketjobs,bulldogjob,pracuj",
    )
    report = {"run_id":run_id,"target_per_source":args.target_per_source,"sources":[]}
    manifest = {"sources":{}}
    try:
        with httpx.Client(
            timeout=35, follow_redirects=True,
            headers={"User-Agent":USER_AGENT,"Accept-Language":"pl,en;q=0.8"},
        ) as client:
            source_report, rows = _run_nfj(client, store, run_id, args.target_per_source, args.delay)
            report["sources"].append(source_report); manifest["sources"]["nofluffjobs"] = rows
            for source in ("rocketjobs","bulldogjob"):
                source_report, rows = _run_direct_html(
                    client, store, run_id, source, args.target_per_source, args.delay
                )
                report["sources"].append(source_report); manifest["sources"][source] = rows
            source_report, rows = _run_pracuj_mirror(client, store, run_id, args.target_per_source)
            report["sources"].append(source_report); manifest["sources"]["pracuj"] = rows
        report["new_match_candidates"] = store.generate_match_candidates()
        report["database"] = store.summary()
        report["insufficient_sources"] = [
            s["source"] for s in report["sources"]
            if s.get("successes",0) < args.target_per_source
        ]
        store.finish_run(
            run_id,
            status="PARTIAL" if report["insufficient_sources"] else "COMPLETED",
            summary=report,
        )
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        store.finish_run(run_id, status="FAILED", summary=report)
        raise
    for path, value in ((args.report,report),(args.manifest,manifest)):
        out = Path(path); out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report["insufficient_sources"]:
        raise SystemExit(f"insufficient sources: {report['insufficient_sources']}")

if __name__ == "__main__":
    main()
