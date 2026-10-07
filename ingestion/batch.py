from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

import httpx

from .sources import ADAPTERS
from .storage import PostgresStore
from .theprotocol_mcp import fetch_batch_sync, fetch_groups_sync, parse as parse_theprotocol


USER_AGENT = "job-market-knowledge-graph/CRAWL-02 (+https://github.com/ryba-22/job-market-knowledge-graph)"


def _load_manifest(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    return json.loads(p.read_text(encoding="utf-8"))


def run_theprotocol(store, limit: int, manifest_rows: list[dict] | None = None) -> tuple[dict, list[dict]]:
    stats = Counter()
    errors = []
    changes = []
    manifest = []

    if manifest_rows:
        search_rows = [row["search"] for row in manifest_rows]
        gids = [str(row["groupId"]) for row in manifest_rows]
        details_rows = fetch_groups_sync(gids)
        pairs = list(zip(search_rows, details_rows))
    else:
        pairs = fetch_batch_sync(limit)

    for search_row, details in pairs:
        try:
            parsed = parse_theprotocol(search_row, details)
            raw_text = json.dumps(
                {"search": search_row, "details": details},
                ensure_ascii=False,
                sort_keys=True,
            )
            raw_id = store.record_fetch(
                source="theprotocol",
                url=parsed.url or f"mcp://theprotocol/{parsed.source_posting_id}",
                final_url=parsed.url or f"mcp://theprotocol/{parsed.source_posting_id}",
                status=200,
                body=raw_text,
                content_type="application/json; transport=official-mcp",
            )
            result = store.ingest(parsed, raw_id)
            stats[result["state"]] += 1
            if result["state"] == "CHANGED":
                changes.append({
                    "source_posting_id": parsed.source_posting_id,
                    "changed_fields": result.get("changed_fields", []),
                    "change_preview": result.get("change_preview", {}),
                })
            manifest.append({
                "source": "theprotocol",
                "source_posting_id": parsed.source_posting_id,
                "groupId": parsed.source_specific.get("groupId"),
                "url": parsed.url,
                "search": search_row,
            })
        except Exception as exc:
            stats["ERROR"] += 1
            errors.append({"id": search_row.get("offerId"), "error": f"{type(exc).__name__}: {exc}"})

    return ({
        "source": "theprotocol",
        "transport": "official-mcp",
        "discovered": len(pairs),
        "states": dict(stats),
        "changes": changes[:25],
        "errors": errors[:20],
    }, manifest)


def run_jjit(client, store, limit: int, delay: float, manifest_rows: list[dict] | None = None) -> tuple[dict, list[dict]]:
    adapter = ADAPTERS["justjoinit"]
    if manifest_rows:
        from .model import PostingRef
        refs = [
            PostingRef("justjoinit", row["url"], row["source_posting_id"])
            for row in manifest_rows
        ]
    else:
        refs = adapter.discover(client, limit)

    stats = Counter()
    errors = []
    changes = []
    manifest = []
    for ref in refs:
        try:
            response = client.get(ref.url)
            response.raise_for_status()
            raw_id = store.record_fetch(
                source="justjoinit",
                url=ref.url,
                final_url=str(response.url),
                status=response.status_code,
                body=response.text,
                content_type=response.headers.get("content-type"),
            )
            parsed = adapter.parse_detail(response.text, str(response.url))
            result = store.ingest(parsed, raw_id)
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
        time.sleep(delay)

    return ({
        "source": "justjoinit",
        "transport": "ssr-http",
        "discovered": len(refs),
        "states": dict(stats),
        "changes": changes[:25],
        "errors": errors[:20],
    }, manifest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--source", choices=["theprotocol", "justjoinit", "both"], default="both")
    parser.add_argument("--limit-per-source", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.20)
    parser.add_argument("--manifest-in")
    parser.add_argument("--manifest-out")
    parser.add_argument("--report", default="reports/crawl-02-run.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")

    existing_manifest = _load_manifest(args.manifest_in)
    store = PostgresStore(args.dsn)
    store.init_schema()
    report = {"sources": []}
    manifest = {"sources": {}}

    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
    ) as client:
        if args.source in ("theprotocol", "both"):
            source_report, rows = run_theprotocol(
                store,
                args.limit_per_source,
                existing_manifest.get("sources", {}).get("theprotocol"),
            )
            report["sources"].append(source_report)
            manifest["sources"]["theprotocol"] = rows

        if args.source in ("justjoinit", "both"):
            source_report, rows = run_jjit(
                client,
                store,
                args.limit_per_source,
                args.delay,
                existing_manifest.get("sources", {}).get("justjoinit"),
            )
            report["sources"].append(source_report)
            manifest["sources"]["justjoinit"] = rows

    report["new_match_candidates"] = store.generate_match_candidates()
    report["database"] = store.summary()

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
