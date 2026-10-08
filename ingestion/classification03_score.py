"""CLASSIFICATION-03 independent annotations + adjudicated evaluation (fail-closed).

No labels => no precision/recall. Model-produced labels are never used as truth.
The purposive challenge panel cannot be used as a probability population estimate.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

from .classification03 import SOURCE, C02, OUT, QUOTAS, load_verified_population

LABELS = {"IT_TECHNICAL", "NON_IT", "IT_ADJACENT", "UNDETERMINABLE"}
VALID_FAMILIES = {
    "software_engineering", "data_ai", "infrastructure", "security",
    "enterprise_systems", "it_management", "qa_testing", "it_support",
    "tech_sales", "education", "industrial_automation", "telecom_physical",
    "ecommerce_content", "office_admin", "transport_logistics",
    "manufacturing", "marketing", "other", "unknown",
}


def load_export(path: Path, round: str) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("format") != "classification03-annotations-v1" or
            data.get("round") != round or not data.get("reviewer") or
            data.get("independent_attested") is not True or
            not isinstance(data.get("annotations"), list)):
        raise ValueError(f"invalid independent review export ({round})")
    return data


def validate_one(a: dict, record: dict) -> None:
    if a.get("posting_id") != record["posting_id"]:
        raise ValueError("unexpected source posting ID")
    if (a.get("revision_id") != record["revision_id"] or
            a.get("raw_payload_sha256") != record["raw_payload_sha256"]):
        raise ValueError(f"source revision or hash mismatch: {record['posting_id']}")
    if a.get("label") not in LABELS or a.get("family") not in VALID_FAMILIES:
        raise ValueError(f"invalid or missing categorical label/family: {record['posting_id']}")
    label = a["label"]
    notes = (a.get("notes") or "").strip()
    quote = (a.get("quote") or "").strip()
    field = a.get("evidence_field")
    if label in {"IT_ADJACENT", "UNDETERMINABLE"} and len(notes) < 12:
        raise ValueError(f"ambiguous verdict requires explanation: {record['posting_id']}")
    if label in {"IT_TECHNICAL", "NON_IT"} and (not quote or len(quote) < 5):
        raise ValueError(f"confident verdict requires an anchored quote: {record['posting_id']}")
    if label == "IT_TECHNICAL" and field != "description":
        raise ValueError(f"IT_TECHNICAL requires evidence from actual source duties/requirements: {record['posting_id']}")
    if len(quote) > 240:
        raise ValueError(f"evidence over 240-character limit: {record['posting_id']}")
    if quote:
        if field not in ("title", "description", "source_industry"):
            raise ValueError(f"invalid quote field: {record['posting_id']}")
        source = " ".join(str(record.get(field) or "").split())
        actual = " ".join(quote.split())
        if actual not in source:
            raise ValueError(f"ungrounded evidence quote: {record['posting_id']}")


def check_round(data: dict, rows: list[dict], *, strict: bool) -> tuple[dict, list]:
    reference = {r["posting_id"]:r for r in rows}
    if len(reference) != len(rows):
        raise ValueError("duplicate reviewer packet ID")
    result = {}
    for a in data["annotations"]:
        id = a.get("posting_id")
        if id not in reference or id in result:
            raise ValueError(f"unknown or duplicate review row: {id}")
        validate_one(a, reference[id])
        result[id] = a
    missing = sorted(set(reference) - set(result))
    if strict and missing:
        raise ValueError(f"missing {len(missing)} expected annotations")
    return result, missing


def weighted_rates(gold: dict, model_decisions: dict, selection: list[dict]) -> dict:
    sampled = [row for row in selection if row["panel"] == "probability"]
    # Only this panel uses random sampling within frozen model-decision strata.
    if len(sampled) != sum(QUOTAS.values()):
        raise ValueError("incorrect probability panel")
    population_strata = Counter(x["assessment"]["status"] for x in model_decisions.values())
    if any(population_strata[s] < QUOTAS[s] for s in QUOTAS):
        raise ValueError("sampling quota larger than current source population")
    weighted_counts = Counter()
    confusions = Counter()
    for row in sampled:
        id = row["posting_id"]
        actual = gold[id]["label"]
        predicted = model_decisions[id]["assessment"]["status"]
        if predicted != row["stratum"]:
            raise ValueError("prediction changed since sample was frozen")
        w = population_strata[predicted] / QUOTAS[predicted]
        weighted_counts[f"gold_{actual}"] += w
        weighted_counts["eligible_total"] += w
        confusions[f"{actual} -> {predicted}"] += 1
        if actual == "UNDETERMINABLE":
            weighted_counts["unknown_gold_weight"] += w
            continue
        weighted_counts["known_gold_weight"] += w
        if predicted == "IT_CONFIRMED":
            weighted_counts["auto_it_weight"] += w
            if actual == "IT_TECHNICAL":
                weighted_counts["tp_it"] += w
            else:
                weighted_counts["fp_it"] += w
        elif actual == "IT_TECHNICAL":
            weighted_counts["fn_it"] += w
        if actual == "IT_TECHNICAL" and predicted == "NON_IT_CONFIRMED":
            weighted_counts["wrong_nonit_exclusion_weight"] += w
        if actual == "IT_TECHNICAL" and predicted == "REVIEW_REQUIRED":
            weighted_counts["it_abstained_weight"] += w
        if actual in {"NON_IT", "IT_ADJACENT"} and predicted == "NON_IT_CONFIRMED":
            weighted_counts["correct_nonit_weight"] += w
        if predicted == "REVIEW_REQUIRED":
            weighted_counts["abstained_weight"] += w

    def div(a,b): return round(a/b, 4) if b else None
    # Precision/recall target a strict *technical IT job*, not IT-industry membership.
    return {
        "population": 509,
        "probability_panel_size": len(sampled),
        "estimand": "technical-IT occupation among 509 Aplikuj category postings, not current unique market vacancies",
        "it_precision": div(weighted_counts["tp_it"], weighted_counts["tp_it"]+weighted_counts["fp_it"]),
        "it_recall": div(weighted_counts["tp_it"], weighted_counts["tp_it"]+weighted_counts["fn_it"]),
        "technical_it_count_estimate": round(weighted_counts["gold_IT_TECHNICAL"], 1),
        "undeterminable_count_weighted": round(weighted_counts["unknown_gold_weight"],1),
        "known_gold_total_weighted": round(weighted_counts["known_gold_weight"],1),
        "model_review_technical_it_misses_weighted": round(weighted_counts["it_abstained_weight"],1),
        "model_wrong_nonit_technical_it_weighted": round(weighted_counts["wrong_nonit_exclusion_weight"],1),
        "model_false_it_assignments_weighted": round(weighted_counts["fp_it"],1),
        "model_auto_it_precision_denominator_weighted": round(weighted_counts["tp_it"]+weighted_counts["fp_it"],1),
        "confusion_unweighted": dict(sorted(confusions.items())),
        "no_confidence_intervals": "Compute design-consistent CIs before making statistically precise claims; these are point estimates",
        "excludes": "Purpose-selected challenge cases; uncertain gold cases from precision/recall denominators",
    }


def evaluate(source: Path=SOURCE, c02: Path=C02, root: Path=OUT,
             reviewer_a: Path | None=None, reviewer_b: Path | None=None,
             adjudications: Path | None=None) -> dict:
    private = root / "private-sample-manifest.json"
    if not private.exists():
        return {"status":"BLOCKED_NO_SAMPLE", "metrics":None}
    gold_freeze = root / "gold-freeze.json"
    if gold_freeze.exists():
        locked=json.loads(gold_freeze.read_text(encoding="utf-8"))
        if (locked.get("format")!="classification03-independent-gold-freeze-v1" or
                locked.get("input_sha256") != lock_input_fingerprints(root)):
            raise ValueError("FROZEN_GOLD_INPUT_CHANGED: reversioning required")
    manifest = json.loads(private.read_text(encoding="utf-8"))
    selection = manifest["selection"]
    rows_a = [json.loads(s) for s in (root/"reviewer-a.jsonl").read_text(encoding="utf-8").splitlines() if s]
    rows_b = [json.loads(s) for s in (root/"reviewer-b.jsonl").read_text(encoding="utf-8").splitlines() if s]
    a_path = reviewer_a or root / "reviewer-a-annotations.json"
    b_path = reviewer_b or root / "reviewer-b-annotations.json"
    a = load_export(a_path, "a")
    b = load_export(b_path, "b")
    if not a:
        return {"status":"BLOCKED_NO_INDEPENDENT_GOLD", "reviewed_a":0,
                "required_a":200, "required_b":40, "metrics":None}
    as_map, a_missing = check_round(a, rows_a, strict=False)
    if a_missing:
        return {"status":"BLOCKED_INCOMPLETE_FIRST_REVIEW","reviewed_a":len(as_map),
                "required_a":200,"missing_a":len(a_missing),"metrics":None}
    if not b:
        return {"status":"BLOCKED_SECOND_REVIEW","reviewed_a":200,
                "reviewed_b":0,"required_b":40,"metrics":None}
    if a["reviewer"] == b["reviewer"]:
        raise ValueError("second reviewer must have a distinct identity")
    bs_map,b_missing=check_round(b,rows_b,strict=False)
    if b_missing:
        return {"status":"BLOCKED_INCOMPLETE_SECOND_REVIEW","reviewed_a":200,
                "reviewed_b":len(bs_map),"required_b":40,"missing_b":len(b_missing),"metrics":None}
    discrepancies = []
    for id,second in bs_map.items():
        first = as_map[id]
        # Family disagreements also require adjudication. Evidence quotes may differ harmlessly.
        if first["label"] != second["label"] or first["family"] != second["family"]:
            discrepancies.append(id)
    gold = dict(as_map)
    adjud_path = adjudications or root / "adjudications.json"
    if discrepancies:
        if not adjud_path.exists():
            third=load_export(root / "reviewer-c-annotations.json", "c")
            if third:
                if third["reviewer"] in (a["reviewer"], b["reviewer"]):
                    raise ValueError("third reviewer identity must be distinct")
                c_packet=root / "reviewer-c.jsonl"
                if not c_packet.exists():
                    raise ValueError("third-review packet not prepared")
                c_rows=[json.loads(s) for s in c_packet.read_text(encoding="utf-8").splitlines() if s]
                if {r["posting_id"] for r in c_rows} != set(discrepancies):
                    raise ValueError("third-review packet mismatches actual disputes")
                third_map,missing_c=check_round(third,c_rows,strict=False)
                if missing_c:
                    return {"status":"BLOCKED_INCOMPLETE_THIRD_REVIEW","missing_c":len(missing_c),"metrics":None}
                gold.update(third_map)
            else:
                return {"status":"BLOCKED_PENDING_ADJUDICATION","disagreement_count":len(discrepancies),
                        "disagreement_ids":sorted(discrepancies),"metrics":None}
        else:
            adjud = json.loads(adjud_path.read_text(encoding="utf-8"))
            if (adjud.get("format")!="classification03-adjudications-v1" or
                    not adjud.get("adjudicator") or
                    adjud.get("adjudicator") in (a["reviewer"],b["reviewer"])):
                raise ValueError("adjudication needs separately identified third adjudicator")
            entries = adjud.get("annotations")
            if not isinstance(entries,list) or {e.get("posting_id") for e in entries} != set(discrepancies) or len(entries)!=len(discrepancies):
                raise ValueError("incomplete or extra adjudications")
            reference={r["posting_id"]:r for r in rows_a}
            for entry in entries:
                validate_one(entry,reference[entry["posting_id"]])
                gold[entry["posting_id"]]=entry
    original,decisions=load_verified_population(source,c02)
    if (manifest["source_c02_sha256"] !=
            __import__("hashlib").sha256((c02/"assessments.jsonl.gz").read_bytes()).hexdigest()):
        raise ValueError("Frozen model predictions have changed: eval is invalid")
    if set(gold) != {r["posting_id"] for r in selection}:
        raise ValueError("final gold identity coverage mismatch")
    panel=weighted_rates(gold,decisions,selection)
    challenge=[r for r in selection if r["panel"]=="challenge"]
    stress=Counter()
    holdout=Counter()
    for item in selection:
        id=item["posting_id"]
        actual=gold[id]["label"]
        pred=decisions[id]["assessment"]["status"]
        if item["panel"]=="challenge":
            stress[f"{actual} -> {pred}"]+=1
        if item["split"]=="holdout":
            holdout[f"{actual} -> {pred}"]+=1
    possible_unsafe={
        "confident_it_on_human_non_it_or_adjacent":sum(1 for id,g in gold.items()
            if g["label"] in ("NON_IT","IT_ADJACENT") and decisions[id]["assessment"]["status"]=="IT_CONFIRMED"),
        "confident_non_it_on_human_technical_it":sum(1 for id,g in gold.items()
            if g["label"]=="IT_TECHNICAL" and decisions[id]["assessment"]["status"]=="NON_IT_CONFIRMED"),
        "confident_on_human_undeterminable":sum(1 for id,g in gold.items()
            if g["label"]=="UNDETERMINABLE" and decisions[id]["assessment"]["status"]!="REVIEW_REQUIRED"),
    }
    return {
        "status":"EVALUATED_INDEPENDENT_GOLD_RELEASE_APPROVAL_REQUIRED",
        "independent_reviewer_ids":[a["reviewer"],b["reviewer"]],
        "adjudicated_disagreements":len(discrepancies),
        "gold_count":len(gold),"double_review_count":len(bs_map),
        "holdout_count":len(holdout) and sum(holdout.values()),
        "stratified_probability_metrics":panel,
        "challenge_confusion_unweighted":dict(sorted(stress.items())),
        "holdout_confusion_unweighted":dict(sorted(holdout.items())),
        "unsafe_decision_counts_in_reviewed_200":possible_unsafe,
        "release_decision":"NOT_AUTHORIZED: requires domain-owner thresholds and separate approval",
        "caveat":"Reviewer identity/independence is attested, not cryptographically proven. Human adjudication is required.",
    }


def lock_input_fingerprints(root: Path) -> dict:
    from hashlib import sha256
    keep = [
        "private-sample-manifest.json", "reviewer-a-annotations.json",
        "reviewer-b-annotations.json", "adjudications.json",
        "reviewer-c-annotations.json",
    ]
    return {name:sha256((root/name).read_bytes()).hexdigest()
            for name in keep if (root/name).exists()}


def freeze_gold(root: Path=OUT, source: Path=SOURCE, c02: Path=C02) -> dict:
    report=evaluate(source,c02,root)
    if report.get("status")!="EVALUATED_INDEPENDENT_GOLD_RELEASE_APPROVAL_REQUIRED":
        raise ValueError("cannot freeze incomplete/unadjudicated gold")
    snapshot={
        "format":"classification03-independent-gold-freeze-v1",
        "input_sha256":lock_input_fingerprints(root),
        "reviewer_ids":report["independent_reviewer_ids"],
        "gold_count":report["gold_count"],
        "double_review_count":report["double_review_count"],
        "adjudicated_disagreements":report["adjudicated_disagreements"],
        "independent_reviewer_attestation_not_cryptographic_proof":True,
    }
    path=root/"gold-freeze.json"
    content=json.dumps(snapshot,ensure_ascii=False,indent=2)+"\n"
    if path.exists() and path.read_text(encoding="utf-8")!=content:
        raise ValueError("frozen independent gold differs; must version a new checkpoint")
    if not path.exists():
        path.write_text(content,encoding="utf-8")
    return {"status":"GOLD_FROZEN","gold_count":report["gold_count"],"path":str(path)}


def prepare_third_review(root: Path=OUT) -> dict:
    """Generate a blind third-review packet only for actual A/B disagreements."""
    a=load_export(root/"reviewer-a-annotations.json","a")
    b=load_export(root/"reviewer-b-annotations.json","b")
    if not a or not b:
        return {"status":"BLOCKED_REQUIRES_COMPLETE_A_AND_B"}
    if a["reviewer"] == b["reviewer"]:
        raise ValueError("third review cannot arbitrate an identical reviewer")
    a_rows=[json.loads(x) for x in (root/"reviewer-a.jsonl").read_text(encoding="utf-8").splitlines() if x]
    b_rows=[json.loads(x) for x in (root/"reviewer-b.jsonl").read_text(encoding="utf-8").splitlines() if x]
    reviewed_a,missing_a=check_round(a,a_rows,strict=False)
    reviewed_b,missing_b=check_round(b,b_rows,strict=False)
    if missing_a or missing_b:
        return {"status":"BLOCKED_REQUIRES_COMPLETE_A_AND_B",
                "missing_a":len(missing_a),"missing_b":len(missing_b)}
    conflicts={id for id,item in reviewed_b.items()
               if item["label"]!=reviewed_a[id]["label"] or item["family"]!=reviewed_a[id]["family"]}
    packet=[r for r in b_rows if r["posting_id"] in conflicts]
    path=root/"reviewer-c.jsonl"
    content="".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in packet)
    if path.exists() and path.read_text(encoding="utf-8")!=content:
        raise ValueError("old third-review packet differs; freeze or archive before replacing")
    if not path.exists():
        path.write_text(content,encoding="utf-8")
    if packet:
        from .classification03_ui import write_reviewers
        write_reviewers(root)
    return {"status":"THIRD_REVIEW_PACKET_READY" if packet else "NO_DISAGREEMENTS",
            "disagreements":len(conflicts),"packet_path":str(path),
            "reviewer_c_html":str(root/"reviewer-c.html") if packet else None}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=OUT)
    p.add_argument("--source",type=Path,default=SOURCE)
    p.add_argument("--c02",type=Path,default=C02)
    p.add_argument("--reviewer-a",type=Path)
    p.add_argument("--reviewer-b",type=Path)
    p.add_argument("--adjudications",type=Path)
    p.add_argument("--prepare-third-reviewer",action="store_true")
    p.add_argument("--freeze-gold",action="store_true")
    p.add_argument("--out",type=Path,default=Path("reports/classification-03/evaluation.json"))
    args=p.parse_args()
    if args.prepare_third_reviewer:
        print(json.dumps(prepare_third_review(args.root),ensure_ascii=False,indent=2))
        return
    if args.freeze_gold:
        print(json.dumps(freeze_gold(args.root,args.source,args.c02),ensure_ascii=False,indent=2))
        return
    result=evaluate(args.source,args.c02,args.root,args.reviewer_a,args.reviewer_b,args.adjudications)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
