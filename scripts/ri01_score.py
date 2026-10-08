#!/usr/bin/env python3
"""Evaluate explicit, manual RI-01 reviews; abstain if none are complete.

Scoring convention: each reviewed candidate ACCEPT -> TP, REJECT -> FP;
each manually supplied missing source-grounded assertion -> FN. A rejected
misclassified claim must be also supplied as a corrected missing assertion.
These metrics reflect the reviewed sample only, not entire market.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local-evidence/ri01"


def evaluate(review_file: Path, packet_file=OUT / "review-packets.jsonl", claim_file=OUT / "assertion-candidates.jsonl"):
    packets = {p["posting_id"]: p for p in map(json.loads, packet_file.open(encoding="utf-8"))}
    assertions = {}
    by_posting = {}
    for a in map(json.loads, claim_file.open(encoding="utf-8")):
        assertions[a["assertion_id"]] = a
        by_posting.setdefault(a["posting_id"], set()).add(a["assertion_id"])
    reviews = json.loads(review_file.read_text(encoding="utf-8"))
    if reviews.get("format") != "ri01-manual-reviews-v1" or not isinstance(reviews.get("reviews"), list):
        raise ValueError("Invalid review export")
    covered = set()
    tp = fp = fn = 0
    errors = []
    by_modality = {}
    for review in reviews["reviews"]:
        postid = review.get("posting_id")
        if review.get("review_status") != "REVIEWED":
            continue
        if postid not in packets:
            errors.append(f"Unknown posting: {postid}")
            continue
        if postid in covered:
            errors.append(f"Duplicate review: {postid}")
            continue
        if review.get("revision_id") != packets[postid]["revision_id"]:
            errors.append(f"Revision mismatch: {postid}")
            continue
        if not (review.get("reviewer") or reviews.get("reviewer")):
            errors.append(f"Missing reviewer: {postid}")
            continue
        decisions = review.get("decisions") or {}
        expected = by_posting.get(postid, set())
        if set(decisions) != expected or any(v not in ("ACCEPT", "REJECT") for v in decisions.values()):
            errors.append(f"Incomplete candidate decisions: {postid}")
            continue
        missing = []
        for line in (review.get("missing") or "").splitlines():
            if not line.strip():
                continue
            mode, sep, quote = line.partition("|")
            mode, quote = mode.strip(), quote.strip()
            if not sep or mode not in ("MUST", "NICE", "TASK", "UNKNOWN") or not quote:
                errors.append(f"Malformed manual assertion: {postid}: {line[:80]}")
                continue
            # Review packet contains a preview only: exact-source validation
            # of newly added gold claims must be performed against full corpus
            # at the next human gold freeze gate.
            missing.append((mode, quote))
        covered.add(postid)
        tp += sum(1 for verdict in decisions.values() if verdict == "ACCEPT")
        fp += sum(1 for verdict in decisions.values() if verdict == "REJECT")
        fn += len(missing)
        for aid, verdict in decisions.items():
            mode = assertions[aid]["modality_candidate"]
            c = by_modality.setdefault(mode, Counter())
            c["tp" if verdict == "ACCEPT" else "fp"] += 1
        for mode, _ in missing:
            by_modality.setdefault(mode, Counter())["fn"] += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    ready = not errors and len(covered) >= 150
    return {
        "status": "EVALUATED_REVIEWED_SUBSET" if covered else "NO_MANUAL_GOLD",
        "release_gate": "CANDIDATE_EVAL_ONLY" if ready else "BLOCKED",
        "reviewed_postings": len(covered),
        "reviewed_postings_required": 150,
        "tp_accepted_candidates": tp,
        "fp_rejected_candidates": fp,
        "fn_manually_added_assertions": fn,
        "precision": precision,
        "recall": recall,
        "by_modality": {k: dict(v) for k, v in sorted(by_modality.items())},
        "errors": errors,
        "limitations": [
            "Single-reviewer labels are not independent adjudication.",
            "Missing claim anchoring against complete original text remains a separate freeze gate.",
            "Source IT classification and opportunity deduplication remain unverified.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", required=True, help="Manual export from reviewer.html")
    args = parser.parse_args()
    result = evaluate(Path(args.review))
    (OUT / "review-evaluation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
