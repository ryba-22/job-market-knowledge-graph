"""CLASSIFICATION-03 silver triage: blind human review of uncertainty, conflict, audit.

AI suggestions are never stored as independent gold. Human packets contain
original source only and no model labels/confidence/prior reasons.
"""
from __future__ import annotations
from collections import Counter
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .classification03 import OUT, load_verified_population
from .classification03_ai import SILVER, load_packets, validate_model_output
from .classification03_score import check_round, load_export
from .classification03_ui import write_reviewers

VERSION = "classification03-silver-human-triage-v1"
TIER_ORDER = {"CRITICAL_DISAGREEMENT":0,"AI_AMBIGUOUS":1,"LOW_CONFIDENCE":2,"CONTROL_STRATIFIED":3}
CONTROL_QUOTAS = {"IT_CONFIRMED":12,"NON_IT_CONFIRMED":12,"REVIEW_REQUIRED":16}


def deterministic(*values):
    return sha256("|".join(map(str,(VERSION,*values))).encode("utf-8")).hexdigest()


def triage(root:Path=OUT, silver:Path=SILVER, report:Path|None=Path("reports/classification-03/silver-triage.json")) -> dict:
    private=root/"private-sample-manifest.json"
    if not private.exists():
        raise ValueError("missing locked C03 sample")
    sampled=json.loads(private.read_text(encoding="utf-8"))["selection"]
    packets=load_packets(root/"reviewer-a.jsonl")
    source_by_id={x["posting_id"]:x for x in packets}
    sidecar=silver/"silver-annotations.jsonl"
    if not sidecar.exists():
        raise ValueError("AI silver incomplete — no complete verified 200-offer sidecar")
    ai=[json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines() if line]
    valid=validate_model_output(packets, {"annotations":ai})
    silver_by_id={x["posting_id"]:x for x in valid}
    source,c02=load_verified_population()
    ids=set(source_by_id)
    if set(silver_by_id)!=ids:
        raise ValueError("AI silver and source IDs mismatch")
    for id in ids:
        if (source[id]["revision_id"]!=source_by_id[id]["revision_id"] or
                source[id]["raw_payload_sha256"]!=source_by_id[id]["raw_payload_sha256"]):
            raise ValueError(f"blind packet differs from verified source revision: {id}")
    root.mkdir(parents=True,exist_ok=True)
    selected_by_id={row["posting_id"]:row for row in sampled}
    # Fixed 40-case stratified human control from the *probability* sample;
    # selected by source identities + strata, not AI responses.
    controls=set()
    for stratum,n in CONTROL_QUOTAS.items():
        possible=[x["posting_id"] for x in sampled if x["panel"]=="probability" and x["stratum"]==stratum]
        chosen=sorted(possible,key=lambda id:deterministic("control",stratum,id))[:n]
        if len(chosen)!=n:raise ValueError("incomplete random control stratum")
        controls.update(chosen)
    assert len(controls)==40
    review={}
    for id in sorted(ids):
        assessment=silver_by_id[id]
        predicted=c02[id]["assessment"]["status"]
        human_label=assessment["label"]
        critical=(
           (predicted=="IT_CONFIRMED" and human_label in ("NON_IT","IT_ADJACENT","UNDETERMINABLE"))
           or (predicted=="NON_IT_CONFIRMED" and human_label in ("IT_TECHNICAL","IT_ADJACENT","UNDETERMINABLE"))
        )
        reasons=[]
        if critical:reasons.append("CRITICAL_DISAGREEMENT")
        if human_label in ("IT_ADJACENT","UNDETERMINABLE"):reasons.append("AI_AMBIGUOUS")
        if assessment["confidence"]=="low":reasons.append("LOW_CONFIDENCE")
        if id in controls:reasons.append("CONTROL_STRATIFIED")
        if reasons:
            review[id]={
                "posting_id":id,
                "reasons":sorted(reasons,key=lambda reason:TIER_ORDER[reason]),
                "priority":min(TIER_ORDER[reason] for reason in reasons),
                "ai_label":human_label,"ai_confidence":assessment["confidence"],
                "classifier_status":predicted,
                "source_revision_id":source_by_id[id]["revision_id"],
                "raw_payload_sha256":source_by_id[id]["raw_payload_sha256"],
                "panel":selected_by_id[id]["panel"]
            }
    ordered=sorted(review,key=lambda id:(review[id]["priority"],deterministic("human",id)))
    # Do not replace already issued queue or existing human labels without a
    # new explicitly versioned checkpoint. Assessment revision remains frozen.
    manifest=root/"silver-human-triage-manifest.json"
    private_hash=sha256(sidecar.read_bytes()).hexdigest()
    configuration={
        "format":VERSION,"selection_sha256":sha256(private.read_bytes()).hexdigest(),
        "silver_sha256":private_hash,"human_controls":sorted(controls),
        "selected":[{"posting_id":id,"reasons":review[id]["reasons"]} for id in ordered],
    }
    text=json.dumps(configuration,ensure_ascii=False,indent=2)+"\n"
    if manifest.exists() and manifest.read_text(encoding="utf-8")!=text:
        raise ValueError("human review queue changed; refusing silent resampling")
    if not manifest.exists():manifest.write_text(text,encoding="utf-8")
    blind_items=[source_by_id[id] for id in ordered]
    packet_file=root/"reviewer-human.jsonl"
    content="".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in blind_items)
    if packet_file.exists() and packet_file.read_text(encoding="utf-8")!=content:
        raise ValueError("human blind packet changed")
    if not packet_file.exists():packet_file.write_text(content,encoding="utf-8")
    write_reviewers(root)
    reasons=Counter(reason for id in ordered for reason in review[id]["reasons"])
    counts=Counter(item["label"] for item in valid)
    confidence=Counter(item["confidence"] for item in valid)
    summary={
        "checkpoint":"CLASSIFICATION-03-AI-HUMAN-TRIAGE",
        "status":"HUMAN_REVIEW_QUEUE_READY_GOLD_STILL_BLOCKED",
        "ai_silver_count":len(valid),"ai_silver_label_counts":dict(sorted(counts.items())),
        "ai_silver_confidence_counts":dict(sorted(confidence.items())),
        "human_queue_unique":len(ordered),
        "high_priority_flagged_unique":sum(1 for id in ordered if any(r!="CONTROL_STRATIFIED" for r in review[id]["reasons"])),
        "additional_priority_outside_control":sum(1 for id in ordered if id not in controls),
        "stratified_random_control_unique":len(controls),
        "review_reason_counts_overlapping":dict(sorted(reasons.items())),
        "human_review_received":0,
        "blind_human_packet":str(packet_file),
        "human_reviewer_html":str(root/"reviewer-human.html"),
        "all_inputs_revision_verified":True,
        "no_independent_gold":True,
        "classification02_metrics_release":"BLOCKED",
        "measurement_limitations":[
            "Human-triage queue intentionally enriches ambiguous/disagreement cases; pooled counts not representative.",
            "40 random controls selected with fixed quotas from the 160 stratified-probability panel; no uncertainty intervals.",
            "Original 200-offer independent-gold benchmark remains separately blocked until independent labels.",
            "AI-silver labels cannot automatically count as human gold, nor as independent precision/recall.",
        ],
    }
    if report:
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


def human_compare(root:Path=OUT, silver:Path=SILVER) -> dict:
    packet=root/"reviewer-human.jsonl"
    if not packet.exists():
        return {"status":"BLOCKED_NO_TRIAGE"}
    source=[json.loads(s) for s in packet.read_text(encoding="utf-8").splitlines() if s]
    submitted=load_export(root/"reviewer-human-annotations.json","human")
    if not submitted:
        return {"status":"BLOCKED_NO_HUMAN_REVIEWS","expected":len(source),"received":0}
    checked,missing=check_round(submitted,source,strict=False)
    ai={json.loads(s)["posting_id"]:json.loads(s) for s in (silver/"silver-annotations.jsonl").read_text(encoding="utf-8").splitlines() if s}
    agreements=Counter()
    mismatches=[]
    for id,item in checked.items():
        model_label=ai[id]["label"]
        human_label=item["label"]
        agreements[f"{human_label} -> {model_label}"]+=1
        if human_label!=model_label:
            mismatches.append(id)
    return {
        "status":"HUMAN_TRIAGE_PARTIAL" if missing else "HUMAN_TRIAGE_COMPLETE",
        "source_population":len(source),
        "human_reviewed":len(checked),
        "missing":len(missing),
        "agreement_unweighted":dict(sorted(agreements.items())),
        "disagreement_count":len(mismatches),
        "disagreement_ids":sorted(mismatches),
        "not_independent_gold":True,
        "not_unbiased_quality_score":True,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--score-human",action="store_true")
    args=p.parse_args()
    report=human_compare() if args.score_human else triage()
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
