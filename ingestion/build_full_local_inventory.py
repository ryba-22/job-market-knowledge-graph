from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import httpx

from .expansion_sources import SOURCES
from .plan_inventory_chunks import plan as plan_chunks
from .scale_acquisition import load_known_ids
from .sources import ADAPTERS
from .theprotocol_mcp import discover_offers_sync

DEFAULT_SOURCES = (
    "justjoinit",
    "theprotocol",
    "nofluffjobs",
    "rocketjobs",
    "bulldogjob",
    "solidjobs",
    "teamquest",
    "aplikuj",
    "itleaders",
    "michaelpage",
    "eurotechjobs",
    "hnwhoishiring",
    "pracuj",
)
USER_AGENT = "job-market-knowledge-graph/FULL-LOCAL-INVENTORY"


def _discover(client: httpx.Client, source: str):
    adapter = ADAPTERS[source] if source in ADAPTERS else SOURCES[source]
    return adapter.discover(client, 100000)


def build(base_corpus: str, out_dir: str, sources: list[str], chunk_size: int = 250) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    per_source = {}
    with httpx.Client(
        timeout=90,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.8"},
    ) as client:
        for source in sources:
            try:
                known = load_known_ids(base_corpus, source)
                if source == "theprotocol":
                    offers = discover_offers_sync(100000)
                    source_rows = []
                    for offer in offers:
                        sid = str(offer.get("offerId") or offer.get("id") or offer.get("groupId") or offer.get("groupID") or "")
                        gid = str(offer.get("groupId") or offer.get("groupID") or "")
                        if not sid or not gid:
                            continue
                        source_rows.append({
                            "source": source,
                            "source_posting_id": sid,
                            "url": str(offer.get("offerUrl") or offer.get("url") or ""),
                            "known": sid in known,
                            "group_id": gid,
                            "mcp_search_row": offer,
                        })
                else:
                    refs = _discover(client, source)
                    source_rows = [
                        {
                            "source": source,
                            "source_posting_id": str(ref.source_posting_id),
                            "url": ref.url,
                            "known": str(ref.source_posting_id) in known,
                        }
                        for ref in refs
                    ]
                source_rows.sort(key=lambda r: r["source_posting_id"])
                per_source[source] = {
                    "discoverable": len(source_rows),
                    "known": sum(1 for r in source_rows if r["known"]),
                    "unknown": sum(1 for r in source_rows if not r["known"]),
                    "error": None,
                }
                rows.extend(source_rows)
            except Exception as exc:
                per_source[source] = {
                    "discoverable": 0,
                    "known": 0,
                    "unknown": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            print(json.dumps({"source": source, **per_source[source]}, ensure_ascii=False), flush=True)
    rows.sort(key=lambda r: (r["source"], r["source_posting_id"]))
    raw = ("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    comp = gzip.compress(raw, compresslevel=9, mtime=0)
    inventory = out / "inventory.jsonl.gz"
    inventory.write_bytes(comp)
    manifest = {
        "format": "source-inventory-v1",
        "scope": "full-local-acquisition",
        "base_corpus": base_corpus,
        "sources": per_source,
        "discoverable_total": sum(v["discoverable"] for v in per_source.values()),
        "known_total": sum(v["known"] for v in per_source.values()),
        "unknown_total": sum(v["unknown"] for v in per_source.values()),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(comp),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": hashlib.sha256(comp).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan_chunks(str(inventory), str(out / "chunks.json"), chunk_size)
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-corpus", default="data/corpora/corpus-10/corpus.jsonl.gz")
    p.add_argument("--out", default=".local-inventory/full-20261007")
    p.add_argument("--sources", nargs="+", default=list(DEFAULT_SOURCES))
    p.add_argument("--chunk-size", type=int, default=250)
    args = p.parse_args()
    print(json.dumps(build(args.base_corpus, args.out, args.sources, args.chunk_size), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
