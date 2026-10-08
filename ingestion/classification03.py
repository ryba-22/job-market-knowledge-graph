"""CLASSIFICATION-03: source-frozen, prediction-blinded 200-posting evaluation design.

Only source data + C02 *sampling strata* are read here. No candidate status is
exposed in either reviewer packet. No classifier predictions become gold labels.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html import unescape
import argparse
import gzip
import json
from pathlib import Path

from bs4 import BeautifulSoup

from .clean_aplikuj_cache import read_gz
from .run_classification02 import verify_output

SEED = "classification03-20261008-sample-v1"
QUOTAS = {"IT_CONFIRMED": 45, "NON_IT_CONFIRMED": 45, "REVIEW_REQUIRED": 70}
SOURCE = Path(".local-crawl/scale-04-it-v2")
C02 = Path(".local-crawl/classification-02")
OUT = Path(".local-evidence/classification-03")
PUBLIC_SUMMARY = Path("reports/classification-03/sample-design.json")

CHALLENGE_TERMS = (
    "wordpress", "webmaster", "presales", "programista", "informatyk",
    "cyber", "bezpieczen", "robot", "plc", "cnc", "developer", "kierowca",
    "it contracting", "system", "data", "analyst", "analityk", "projektant",
    "wdrozen", "lms", "nauczyciel", "magazyn", "business", "help", "sales",
    "siec", "sap", "telekom", "serwisant", "urzad", "administrat",
)

def fingerprint(data: bytes) -> str:
    return sha256(data).hexdigest()


def ranking(*values: object) -> str:
    return fingerprint("|".join(map(str, (SEED, *values))).encode("utf-8"))


def description(row: dict) -> str:
    semantic = (row.get("normalized_projection") or {}).get("semantic_content") or {}
    structured = semantic.get("jobposting_json_ld") or {}
    html = str(structured.get("description") or "") if isinstance(structured, dict) else ""
    return " ".join(unescape(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)).split())


def load_verified_population(source: Path = SOURCE, c02: Path = C02) -> tuple[dict, dict]:
    result = verify_output(source, c02)
    if result.get("status") != "PASS":
        raise ValueError("CLASSIFICATION-02 source evidence must verify PASS before sampling")
    rows: dict[str,dict] = {}
    for file in sorted((source / "aplikuj").glob("*/corpus.jsonl.gz")):
        for row in read_gz(file):
            ident = str(row["source_posting_id"])
            if ident in rows:
                raise ValueError(f"duplicate source ID: {ident}")
            rows[ident] = row
    decisions = {}
    for assessment in read_gz(c02 / "assessments.jsonl.gz"):
        ident = str(assessment["source_posting_id"])
        if ident in decisions:
            raise ValueError(f"duplicate assessment ID: {ident}")
        decisions[ident] = assessment
    if set(rows) != set(decisions) or len(rows) != 509:
        raise ValueError("incomplete original source / prediction corpus")
    for id, row in rows.items():
        a = decisions[id]
        if a["raw_payload_sha256"] != row["raw_payload_sha256"] or a["revision_id"] != row["revision_id"]:
            raise ValueError(f"prediction source revision changed: {id}")
    return rows, decisions


def choose(rows: dict, decisions: dict) -> list[dict]:
    groups = {s: [] for s in QUOTAS}
    for ident, item in decisions.items():
        status = item["assessment"]["status"]
        if status not in groups:
            raise ValueError(f"unknown model stratum: {status}")
        groups[status].append(ident)
    primary: list[str] = []
    for status, quota in QUOTAS.items():
        if len(groups[status]) < quota:
            raise ValueError(f"not enough examples for stratum {status}")
        order = sorted(groups[status], key=lambda id:(ranking("prob", status, id), id))
        primary.extend(order[:quota])
    if len(primary) != 160 or len(set(primary)) != 160:
        raise ValueError("probability panel duplicate")
    remaining = sorted(set(rows) - set(primary))
    # Challenges are explicitly purposive; exclude them from population estimators.
    def risk_score(ident):
        row = rows[ident]
        a = decisions[ident]
        text = " ".join((row.get("title") or "", str(row["source_projection"].get("industry") or ""))).casefold()
        matched = sum(word in text for word in CHALLENGE_TERMS)
        transition = a["previous_status"] != a["assessment"]["status"]
        return (
            -(matched + 2 * int(transition) + int(a["assessment"]["status"] == "REVIEW_REQUIRED")),
            ranking("challenge", ident), ident,
        )
    challenges = sorted(remaining, key=risk_score)[:40]
    selected = set(primary + challenges)
    if len(selected) != 200:
        raise ValueError("sample size mismatch")
    # Exactly 40 held-out rows, stratified between probability and challenges.
    # The holdout assignments are hidden from reviewers and locked at preparation.
    holdout = set(sorted(primary, key=lambda id: ranking("holdout", id))[:32] +
                  sorted(challenges, key=lambda id: ranking("holdout", id))[:8])
    double = set(sorted(primary, key=lambda id: ranking("dual", id))[:32] +
                 sorted(challenges, key=lambda id: ranking("dual", id))[:8])
    chosen = []
    for ident in sorted(selected, key=lambda id: ranking("presentation", id)):
        panel = "probability" if ident in primary else "challenge"
        chosen.append({
            "posting_id": ident,
            "revision_id": rows[ident]["revision_id"],
            "raw_payload_sha256": rows[ident]["raw_payload_sha256"],
            "panel": panel,
            "stratum": decisions[ident]["assessment"]["status"],
            "split": "holdout" if ident in holdout else "development",
            "second_review_required": ident in double,
        })
    assert len(chosen) == 200 and len(holdout) == 40 and len(double) == 40
    return chosen


def packet(row: dict) -> dict:
    """Only original source content: absolutely no model decisions or strata."""
    return {
        "posting_id": str(row["source_posting_id"]),
        "revision_id": row["revision_id"],
        "raw_payload_sha256": row["raw_payload_sha256"],
        "source": "aplikuj",
        "source_url": row["url"],
        "title": row["title"],
        "source_industry": row["source_projection"].get("industry"),
        "description": description(row),
    }


def export_jsonl(path: Path, rows: list[dict]):
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                    encoding="utf-8")


def prepare(source: Path = SOURCE, c02: Path = C02, out: Path = OUT,
            public: Path | None = PUBLIC_SUMMARY) -> dict:
    rows, decisions = load_verified_population(source, c02)
    design = choose(rows, decisions)
    out.mkdir(parents=True, exist_ok=True)
    internal = out / "private-sample-manifest.json"
    selected_a = [packet(rows[item["posting_id"]]) for item in design]
    selected_b = [packet(rows[item["posting_id"]]) for item in design if item["second_review_required"]]
    sample_manifest = {
        "format": "classification03-locked-sample-v1",
        "seed": SEED, "source_c02_sha256": fingerprint((c02 / "assessments.jsonl.gz").read_bytes()),
        "population_count": len(rows), "quota": QUOTAS, "selection": design,
    }
    serialized = json.dumps(sample_manifest, ensure_ascii=False, indent=2) + "\n"
    if internal.exists() and internal.read_text(encoding="utf-8") != serialized:
        raise ValueError("A DIFFERENT sample manifest already exists. Never overwrite a locked evaluation design.")
    # Stable assignment is a prerequisite for reviewer export. No predictions in packets.
    if not internal.exists():
        internal.write_text(serialized, encoding="utf-8")
    for name, values in (("reviewer-a.jsonl", selected_a), ("reviewer-b.jsonl", selected_b)):
        path = out / name
        fresh = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in values)
        if path.exists() and path.read_text(encoding="utf-8") != fresh:
            raise ValueError(f"Sample packet has changed: {name}")
        if not path.exists():
            path.write_text(fresh, encoding="utf-8")
    from .classification03_ui import write_reviewers
    write_reviewers(out)
    summary = {
        "checkpoint": "CLASSIFICATION-03",
        "source_population": len(rows), "selected": len(design),
        "probability_panel": 160, "challenge_panel": 40,
        "probability_quotas_by_previous_model_decision": QUOTAS,
        "holdout_reserved": 40, "double_review_reserved": 40,
        "blind_packet_fields": sorted(selected_a[0].keys()),
        "source_archive_verified": True,
        "independent_gold_labels_received": 0, "gold_release_gate": "BLOCKED_NO_INDEPENDENT_GOLD",
        "sample_manifest_sha256": fingerprint(serialized.encode("utf-8")),
        "population_estimation": "Only probability panel with fixed stratum weights; challenge panel is adversarial only",
        "limitations": ["Current-site category, not active/recruitment-deduped market",
                        "No independent human gold labels; performance cannot be estimated yet"],
    }
    if public:
        public.parent.mkdir(parents=True, exist_ok=True)
        public.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=SOURCE)
    p.add_argument("--c02", type=Path, default=C02)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--summary", type=Path, default=PUBLIC_SUMMARY)
    args = p.parse_args()
    print(json.dumps(prepare(args.source, args.c02, args.out, args.summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
