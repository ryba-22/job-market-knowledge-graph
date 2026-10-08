#!/usr/bin/env python3
"""Freeze RI-01 variant A without touching the original frozen corpus.

Run once before regenerating .local-evidence/ri01; repeat is idempotent
when the manifest is already present. Writes public metadata-only
selection to data/evals, detailed exclusion audit to local evidence.
"""
import argparse
import gzip
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ingestion.requirement_intelligence import identity, stable_hash
from ingestion.ri01_replacement import REPLACEMENT_QUOTA, select_replacements

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/evals/ri01-variant-a-selection.json"
EVIDENCE = ROOT / ".local-evidence/ri01"
CORPUS = ROOT / "data/corpora/corpus-10/corpus.jsonl.gz"


def main():
    if MANIFEST.exists():
        prior = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if prior.get("format") != "ri01-variant-a-v1":
            raise SystemExit("Existing selection format differs; NO OVERWRITE")
        print(json.dumps({"status": "ALREADY_FROZEN", "manifest": str(MANIFEST),
                          "kept": len(prior["kept"]), "replaced": len(prior["removed"]),
                          "replacement": len(prior["replacement"])}, ensure_ascii=False))
        return
    packets_file = EVIDENCE / "review-packets.jsonl"
    assertions_file = EVIDENCE / "assertion-candidates.jsonl"
    if not packets_file.is_file() or not assertions_file.is_file():
        raise SystemExit("Missing original RI-01 evidence: cannot reconstruct replaced IDs")
    original = [json.loads(line) for line in packets_file.open(encoding="utf-8")]
    existing_assertions = [json.loads(line) for line in assertions_file.open(encoding="utf-8")]
    if len(original) != 200 or len({p["posting_id"] for p in original}) != 200:
        raise SystemExit("Unexpected original sample; cannot safely change selection")
    if any(p.get("review_status") != "UNREVIEWED" for p in original):
        raise SystemExit("Existing reviewed state: require manual migration, not silent rewrite")
    covered = {a["posting_id"] for a in existing_assertions}
    kept = [p for p in original if p["posting_id"] in covered]
    removed = [p for p in original if p["posting_id"] not in covered]
    if len(kept) != 150 or len(removed) != 50:
        raise SystemExit(f"Expected to retain 150 and audit 50; found {len(kept)}, {len(removed)}")
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        corpus = [json.loads(line) for line in f]
    lookup = {identity(r): r for r in corpus}
    if len(lookup) != len(corpus) or any(p["posting_id"] not in lookup for p in original):
        raise SystemExit("Frozen corpus identity mismatch")
    # Ensure none of the originally kept source revisions has changed.
    for p in original:
        if lookup[p["posting_id"]].get("revision_id") != p.get("revision_id"):
            raise SystemExit("Source revision mismatch: " + p["posting_id"])
    kept_records = [lookup[p["posting_id"]] for p in kept]
    replacement, qualification = select_replacements(corpus, set(p["posting_id"] for p in original), kept_records)
    output_ids = [p["posting_id"] for p in kept] + [identity(r) for r in replacement]
    if len(set(output_ids)) != 200 or set(output_ids).intersection(p["posting_id"] for p in removed):
        raise SystemExit("New selection overlaps old removed set")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    audit = {
        "format": "ri01-exclusion-audit-v1",
        "decision": "User explicitly chose option A: replace 50 no-assertion records with complete-text records from frozen CORPUS-10",
        "method": "incomplete_source_record_not_a_negative_requirement",
        "removed": [{"posting_id": p["posting_id"], "source": p["source"],
                     "title": p["title"], "url": p["url"], "revision_id": p["revision_id"],
                     "reason": "ZERO_ASSERTIONS_IN_ORIGINAL_RI01_AND_NO_FULL_REQUIREMENTS_IN_FROZEN_PROJECTION",
                     "original_split": p["split"], "text_preview": p.get("text_preview", "")}
                    for p in removed],
        "source_counts": dict(Counter(p["source"] for p in removed)),
    }
    (EVIDENCE / "variant-a-removed-50-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prior = {
        "format": "ri01-variant-a-v1",
        "decision": "A",
        "corpus": str(CORPUS.relative_to(ROOT)),
        "original_200": [{"posting_id": p["posting_id"], "revision_id": p["revision_id"],
                          "split": p["split"]} for p in original],
        "kept": [{"posting_id": p["posting_id"], "revision_id": p["revision_id"],
                  "split": p["split"]} for p in kept],
        "removed": [{"posting_id": p["posting_id"], "source": p["source"],
                     "revision_id": p["revision_id"]} for p in removed],
        "replacement": [{
            "posting_id": identity(r), "revision_id": r.get("revision_id"),
            "source": r["source"], "quality": qualification[identity(r)],
            "split": "holdout" if int(stable_hash(identity(r)), 16) % 5 == 0 else "development"
        } for r in replacement],
        "policy": {
            "keep_original_valid": 150, "replace_zero_assertion": 50,
            "replacement_quota": REPLACEMENT_QUOTA,
            "no_additional_crawling": True,
            "selection_is_not_manual_gold": True,
            "candidate_scope": "Existing frozen CORPUS-10 only",
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(prior, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "FROZEN", "manifest": str(MANIFEST),
                      "kept": len(kept), "removed": len(removed),
                      "replacements": len(replacement),
                      "replacement_by_source": dict(Counter(r["source"] for r in replacement)),
                      "audit_path": str(EVIDENCE / "variant-a-removed-50-audit.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
