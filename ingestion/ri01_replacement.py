"""RI-01 variant A: replace metadata-only records using the FROZEN corpus only.

No network calls, no auto-labeling as human gold. Keep the original 150 IDs,
archive exactly 50 failed records, and choose deterministic source-complete
replacements with independent, inspectable source-evidence heuristics.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from ingestion.requirement_intelligence import (
    candidate_text, classify_title, identity, language_candidate,
    seniority, source_segments, stable_hash,
)

REPLACEMENT_QUOTA = {
    "nofluffjobs": 12,
    "theprotocol": 10,
    "bulldogjob": 10,
    "solidjobs": 10,
    "justjoinit": 8,
}
assert sum(REPLACEMENT_QUOTA.values()) == 50
TEXT_MIN_CHARS = 900
SEGMENT_MIN = 5


def opportunity_hint(r: dict) -> tuple[str, str] | None:
    """Only a conservative candidate duplicate filter, NOT entity resolution."""
    employer = (r.get("organization_mention_normalized") or r.get("organization_mention") or "").strip().lower()
    title = (r.get("title") or "").strip().lower()
    if not employer or not title:
        return None
    normalized = lambda x: re.sub(r"[^a-z0-9ąćęłńóśźż]+", " ", x).strip()
    return normalized(employer), normalized(title)


def evidence_eligibility(r: dict) -> dict:
    """Preannotation source-content gate; not proof of accurate requirement labels."""
    source = r["source"]
    text = candidate_text(r)
    fragments = source_segments(r)
    modal = Counter(item[2] for item in fragments)
    supported = source in REPLACEMENT_QUOTA
    title = r.get("title") or ""
    family = classify_title(title)
    reasons = []
    if not supported:
        reasons.append("SOURCE_NOT_IN_REPLACEMENT_PLAN")
    if len(text) < TEXT_MIN_CHARS:
        reasons.append("DESCRIPTION_TOO_SHORT")
    if len(fragments) < SEGMENT_MIN:
        reasons.append("TOO_FEW_SOURCE_FRAGMENTS")
    if family == "nontechnical":
        reasons.append("NONTECHNICAL_TITLE")
    explicit = modal["MUST"] + modal["NICE"] + modal["TASK"]
    if source in {"nofluffjobs", "theprotocol", "bulldogjob", "solidjobs"} and explicit < 2:
        reasons.append("NOT_ENOUGH_TYPED_SECTIONS")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "description_chars": len(text),
        "source_fragments": len(fragments),
        "typed_fragments": explicit,
        "family_candidate": family,
        "seniority_candidate": seniority(r),
        "language_candidate": language_candidate(r),
    }


def select_replacements(corpus: list[dict], original_ids: set[str], kept: list[dict]) -> tuple[list[dict], dict]:
    grouped = defaultdict(list)
    duplicate_hints = {h for r in kept if (h := opportunity_hint(r)) is not None}
    quality = {}
    for r in corpus:
        rid = identity(r)
        if rid in original_ids or r["source"] not in REPLACEMENT_QUOTA:
            continue
        hint = opportunity_hint(r)
        if hint is not None and hint in duplicate_hints:
            continue
        check = evidence_eligibility(r)
        if not check["eligible"]:
            continue
        quality[rid] = check
        grouped[r["source"]].append(r)
    replacements = []
    selected_hints = set(duplicate_hints)
    for source, quota in REPLACEMENT_QUOTA.items():
        by_stratum = defaultdict(list)
        for r in grouped[source]:
            check = quality[identity(r)]
            by_stratum[(check["family_candidate"], check["seniority_candidate"], check["language_candidate"])].append(r)
        for bucket in by_stratum.values():
            bucket.sort(key=lambda r: stable_hash(identity(r)))
        # Round-robin independent of corpus ordering. No single family or seniority dominates
        # whenever other eligible strata are available.
        order = sorted(by_stratum, key=lambda k: stable_hash(str(k)))
        chosen = []
        while len(chosen) < quota:
            progressed = False
            for key in order:
                if len(chosen) >= quota:
                    break
                while by_stratum[key]:
                    candidate = by_stratum[key].pop(0)
                    hint = opportunity_hint(candidate)
                    if hint is not None and hint in selected_hints:
                        continue
                    chosen.append(candidate)
                    if hint is not None:
                        selected_hints.add(hint)
                    progressed = True
                    break
            if not progressed:
                break
        if len(chosen) != quota:
            raise ValueError(f"Insufficient full-text {source} replacement candidates: {len(chosen)}/{quota}")
        replacements.extend(chosen)
    if len(replacements) != 50 or len({identity(x) for x in replacements}) != 50:
        raise ValueError("Replacement cardinality/identity violation")
    return replacements, {identity(r): quality[identity(r)] for r in replacements}
