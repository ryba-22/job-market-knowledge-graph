"""Derived priority human queue: 40 original random controls + 12 domain risks.

All controls were selected before AI review. This does NOT generate human gold.
Packets are SOURCE ONLY, with no revealed AI or rule outcomes.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
from pathlib import Path
import argparse,json

from .classification03 import OUT
from .classification03_ai_second import read_items
from .classification03_ui import write_reviewers
from .classification03_score import load_export,check_round

VERSION="classification03-priority-human-v1"
REPORT=Path("reports/classification-03/priority-human-queue.json")

def prepare(root:Path=OUT, report:Path|None=REPORT)->dict:
    src={x["posting_id"]:x for x in read_items(root/"reviewer-human.jsonl")}
    first=json.loads((root/"silver-human-triage-manifest.json").read_text(encoding="utf-8"))
    control=set(first["human_controls"])
    domain=set(json.loads((root/"ai-domain-third-v1"/"comparison.json").read_text(encoding="utf-8"))["disputed_ids"])
    ids=sorted(control|domain,key=lambda id:(id not in domain,sha256(id.encode()).hexdigest()))
    if len(control)!=40 or len(domain)!=12 or len(ids)!=47:
        raise ValueError("priority-review source sample/overlap changed")
    if not set(ids).issubset(src):
        raise ValueError("priority sample must be from original blind 69")
    selection={
        "format":VERSION,
        "controls":sorted(control),"critical_domain":sorted(domain),
        "ordered_ids":ids,
        "human_packet_source_sha256":sha256((root/"reviewer-human.jsonl").read_bytes()).hexdigest(),
    }
    manifest=root/"priority-human-private-manifest.json"
    encoded=json.dumps(selection,ensure_ascii=False,indent=2)+"\n"
    if manifest.exists() and manifest.read_text(encoding="utf-8")!=encoded:
        raise ValueError("locked priority selection differs; must version a new checkpoint")
    if not manifest.exists():manifest.write_text(encoded,encoding="utf-8")
    packets=[src[id] for id in ids]
    exported="".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in packets)
    packet_path=root/"reviewer-priority-human.jsonl"
    if packet_path.exists() and packet_path.read_text(encoding="utf-8")!=exported:
        raise ValueError("source-only priority packet changed")
    if not packet_path.exists():packet_path.write_text(exported,encoding="utf-8")
    write_reviewers(root)
    html=(root/"reviewer-priority-human.html").read_text(encoding="utf-8")
    for leaked in ("IT_CONFIRMED","NON_IT_CONFIRMED","REVIEW_REQUIRED","AI_SILVER_NOT_HUMAN_GOLD"):
        if leaked in html:raise ValueError(f"model data leaked into priority human UI: {leaked}")
    result={
        "checkpoint":"CLASSIFICATION-03-AI-TEAM-PRIORITY-HUMAN",
        "status":"PRIORITY_HUMAN_QUEUE_READY_GOLD_STILL_BLOCKED",
        "source_200":200,
        "ai_second_review_69":69,
        "third_domain_ai_12":12,
        "control_random_stratified_40":40,
        "overlap_5":5,
        "human_review_priority_unique":len(ids),
        "human_completed":0,
        "human_packet":"reviewer-priority-human.jsonl",
        "human_ui":"reviewer-priority-human.html",
        "model_labels_hidden":True,
        "no_independent_human_gold":True,
        "gold_benchmark_release":"BLOCKED",
    }
    if report:
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

def score(root:Path=OUT)->dict:
    path=root/"reviewer-priority-human.jsonl"
    if not path.exists():return {"status":"BLOCKED_NO_PRIORITY_PACKET"}
    docs=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    export=load_export(root/"reviewer-priority-human-annotations.json","priority-human")
    if not export:
        return {"status":"BLOCKED_NO_HUMAN_PRIORITY_REVIEWS","expected":len(docs),"received":0}
    verified,missing=check_round(export,docs,strict=False)
    domain=json.loads((root/"priority-human-private-manifest.json").read_text(encoding="utf-8"))
    flagged=set(domain["critical_domain"])
    reviewed_flags=sum(id in flagged for id in verified)
    result={
        "status":"HUMAN_PRIORITY_REVIEW_COMPLETE" if not missing else "HUMAN_PRIORITY_REVIEW_PARTIAL",
        "expected":len(docs),"received":len(verified),"missing":len(missing),
        "domain_risk_reviewed":reviewed_flags,"domain_risk_required":len(flagged),
        "human_reviewed_labels":dict(sorted(Counter(x["label"] for x in verified.values()).items())),
        "not_full_independent_200_gold":True,
        "release_gate":"BLOCKED",
    }
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--score",action="store_true")
    args=p.parse_args()
    print(json.dumps(score() if args.score else prepare(),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
