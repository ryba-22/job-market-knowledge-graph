from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time
from contextlib import nullcontext

import httpx

from .sources import ADAPTERS
from .storage import PostgresStore


USER_AGENT = "job-market-knowledge-graph/CRAWL-02 (+https://github.com/ryba-22/job-market-knowledge-graph)"


def run_source(client, store, source_code: str, limit: int, delay: float) -> dict:
    adapter = ADAPTERS[source_code]
    stats = Counter()
    errors = []
    try:
        refs = adapter.discover(client, limit)
    except Exception as exc:
        return {
            "source": source_code,
            "discovered": 0,
            "states": {"DISCOVERY_ERROR": 1},
            "errors": [{"url": "discovery", "error": f"{type(exc).__name__}: {exc}"}],
        }

    browser = None
    page = None
    if source_code == "theprotocol":
        from playwright.sync_api import sync_playwright
        browser_runtime = sync_playwright().start()
        browser = browser_runtime.chromium.launch(headless=True)
        page = browser.new_page(locale="pl-PL")
    else:
        browser_runtime = None

    try:
        for ref in refs:
            try:
                if page is not None:
                    response = page.goto(ref.url, wait_until="domcontentloaded", timeout=45000)
                    status = response.status if response else 200
                    html = page.content()
                    final_url = page.url
                    content_type = "text/html; browser-rendered"
                else:
                    response = client.get(ref.url)
                    response.raise_for_status()
                    status = response.status_code
                    html = response.text
                    final_url = str(response.url)
                    content_type = response.headers.get("content-type")
                raw_id = store.record_fetch(
                    source=source_code,
                    url=ref.url,
                    final_url=final_url,
                    status=status,
                    body=html,
                    content_type=content_type,
                )
                parsed = adapter.parse_detail(html, final_url)
                result = store.ingest(parsed, raw_id)
                stats[result["state"]] += 1
            except Exception as exc:
                stats["ERROR"] += 1
                errors.append({"url": ref.url, "error": f"{type(exc).__name__}: {exc}"})
            time.sleep(delay)
    finally:
        if page is not None:
            page.close()
        if browser is not None:
            browser.close()
        if browser_runtime is not None:
            browser_runtime.stop()

    return {
        "source": source_code,
        "discovered": len(refs),
        "states": dict(stats),
        "errors": errors[:20],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--source", choices=["theprotocol", "justjoinit", "both"], default="both")
    parser.add_argument("--limit-per-source", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.20)
    parser.add_argument("--report", default="reports/crawl-02-run.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    store = PostgresStore(args.dsn)
    store.init_schema()
    source_codes = list(ADAPTERS) if args.source == "both" else [args.source]
    report = {"sources": []}
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
    ) as client:
        for source in source_codes:
            report["sources"].append(
                run_source(client, store, source, args.limit_per_source, args.delay)
            )
    report["new_match_candidates"] = store.generate_match_candidates()
    report["database"] = store.summary()

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
