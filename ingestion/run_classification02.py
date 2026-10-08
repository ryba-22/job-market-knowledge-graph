"""CLASSIFICATION-02 offline reassessment from immutable Aplikuj v2 archive.

No network, no source mutation, no assumption that classified = manually verified.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from .classification02 import POLICY_VERSION, assess_row
from .clean_aplikuj_cache import compressed_rows, read_gz
from .verify_aplikuj_v2 import verify as verify_source

DEFAULT_SOURCE = Path(".local-crawl/scale-04-it-v2")
DEFAULT_TARGET = Path(".local-crawl/classification-02")
DEFAULT_SUMMARY = Path("reports/classification-02/summary.json")


def run(source: Path, target: Path, summary_path: Path | None = None) -> dict:
    source_verification = verify_source(source)
    if source_verification["status"] != "PASS" or source_verification["errors"]:
        raise ValueError("source archival verification failed; refusing to reclassify")
    rows = {}
    baseline = {}
    source_fingerprints = {}
    for directory in sorted((source / "aplikuj").glob("*")):
        if not directory.is_dir() or not (directory / "manifest.json").exists():
            continue
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["scope"] != "it-category-v2":
            raise ValueError("legacy chunk in v2 source")
        source_fingerprints[directory.name] = {
            "corpus_sha256": manifest["corpus"]["compressed_sha256"],
            "raw_sha256": manifest["raw_archive"]["compressed_sha256"],
            "assessment_sha256": manifest["assessment_archive"]["compressed_sha256"],
        }
        for row in read_gz(directory / "corpus.jsonl.gz"):
            sid = str(row["source_posting_id"])
            if sid in rows:
                raise ValueError(f"duplicate source identity: {sid}")
            rows[sid] = row
        for item in read_gz(directory / "assessments.jsonl.gz"):
            sid = str(item["source_posting_id"])
            if sid in baseline:
                raise ValueError(f"duplicate baseline identity: {sid}")
            baseline[sid] = item
    if not rows or set(rows) != set(baseline) or len(rows) != source_verification["postings"]:
        raise ValueError("source and baseline identity mismatch")
    decisions = []
    review = []
    status_counts = Counter()
    reason_counts = Counter()
    family_counts = Counter()
    transitions = Counter()
    changed = 0
    for sid in sorted(rows, key=lambda value: (int(value) if value.isdecimal() else float("inf"), value)):
        row = rows[sid]
        assessment = assess_row(row)
        previous = baseline[sid]["assessment"]["status"]
        # Bind decision to the immutable source payload hash and revision identity.
        if baseline[sid]["raw_payload_sha256"] != row["raw_payload_sha256"]:
            raise ValueError(f"payload revision mismatch: {sid}")
        item = {
            "source": "aplikuj", "source_posting_id": sid,
            "revision_id": row["revision_id"], "raw_payload_sha256": row["raw_payload_sha256"],
            "previous_status": previous, "assessment": assessment,
        }
        decisions.append(item)
        status = assessment["status"]
        status_counts[status] += 1
        reason_counts[assessment["reason_code"]] += 1
        family_counts[assessment["role_family"]] += 1
        transitions[f"{previous} -> {status}"] += 1
        if previous != status:
            changed += 1
        if status == "REVIEW_REQUIRED":
            review.append({
                "source_posting_id": sid, "url": row["url"], "title": row["title"],
                "industry": row["source_projection"].get("industry"),
                "raw_payload_sha256": row["raw_payload_sha256"],
                "reason_code": assessment["reason_code"], "role_family": assessment["role_family"],
                "evidence": assessment["evidence"],
            })
    # Confirm output has not lost identity/revision information prior to writing.
    if len(decisions) != len(rows) or len({r["source_posting_id"] for r in decisions}) != len(rows):
        raise ValueError("output identity loss")
    packed, meta = compressed_rows(decisions)
    review_packed, review_meta = compressed_rows(review)
    target.mkdir(parents=True, exist_ok=True)
    decisions_path = target / "assessments.jsonl.gz"
    review_path = target / "review-queue.jsonl.gz"
    # Atomic sidecar writes: source archive is never opened for writing.
    for path, data in ((decisions_path, packed), (review_path, review_packed)):
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
    manifest = {
        "format": "classification-02-sidecar-v1",
        "policy_version": POLICY_VERSION,
        "source_root": str(source),
        "source_chunks": source_verification["v2_chunks"],
        "source_fingerprints": source_fingerprints,
        "source_postings": len(rows),
        "assessments": meta, "review_queue": review_meta,
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "role_families": dict(sorted(family_counts.items())),
        "transitions": dict(sorted(transitions.items())),
        "changed_from_v1": changed,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = verify_output(source, target)
    if result["status"] != "PASS":
        raise RuntimeError(f"failed post-write sidecar verification: {result}")
    summary = {
        "date": datetime.now(timezone.utc).isoformat(),
        "checkpoint": "CLASSIFICATION-02", "source_postings": len(rows),
        "baseline_status_counts": dict(sorted(Counter(x["assessment"]["status"] for x in baseline.values()).items())),
        "status_counts": manifest["status_counts"], "reason_counts": manifest["reason_counts"],
        "role_families": manifest["role_families"], "transitions": manifest["transitions"],
        "changed_from_v1": changed, "review_queue_count": len(review),
        "source_archive_verification": source_verification["status"],
        "assessment_verification": result["status"],
        "is_independently_validated": False,
        "population_note": "Aplikuj IT site category; not deduplicated active technical-IT market",
        "policy_version": POLICY_VERSION,
    }
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def verify_output(source: Path, target: Path) -> dict:
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        return {"status": "NOT_RUN"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    src = verify_source(source)
    if src["status"] != "PASS":
        errors.append("source archival verification not PASS")
    actual_fingerprints = {}
    for d in sorted((source / "aplikuj").glob("*")):
        p = d / "manifest.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text(encoding="utf-8"))
        actual_fingerprints[d.name] = {
            "corpus_sha256": m["corpus"]["compressed_sha256"],
            "raw_sha256": m["raw_archive"]["compressed_sha256"],
            "assessment_sha256": m["assessment_archive"]["compressed_sha256"],
        }
    if actual_fingerprints != manifest["source_fingerprints"]:
        errors.append("original source manifest fingerprint changed")
    result = {}
    for name, key in (("assessments.jsonl.gz", "assessments"), ("review-queue.jsonl.gz", "review_queue")):
        path = target / name
        try:
            blob = path.read_bytes()
            raw = gzip.decompress(blob)
            meta = manifest[key]
            if hashlib.sha256(blob).hexdigest() != meta["compressed_sha256"] or hashlib.sha256(raw).hexdigest() != meta["uncompressed_sha256"]:
                raise ValueError("sha256 mismatch")
            items = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l]
            if len(items) != meta["rows"]:
                raise ValueError("row mismatch")
            result[name] = items
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    if not errors:
        decisions = result["assessments.jsonl.gz"]
        review = result["review-queue.jsonl.gz"]
        ids = [x["source_posting_id"] for x in decisions]
        review_ids = [x["source_posting_id"] for x in review]
        if (len(ids) != len(set(ids)) or len(ids) != manifest["source_postings"] or
                set(review_ids) != {x["source_posting_id"] for x in decisions if x["assessment"]["status"] == "REVIEW_REQUIRED"} or
                len(review_ids) != len(set(review_ids))):
            errors.append("assessment / review-queue identity reconciliation failed")
        counts = Counter(x["assessment"]["status"] for x in decisions)
        if dict(sorted(counts.items())) != manifest["status_counts"]:
            errors.append("classification status counts mismatch")
    return {"status": "PASS" if not errors else "FAIL",
            "source_postings": manifest["source_postings"],
            "review_count": manifest["review_queue"]["rows"],
            "errors": errors}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--out", type=Path, default=DEFAULT_TARGET)
    p.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    result = verify_output(args.source, args.out) if args.verify_only else run(args.source, args.out, args.summary)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
