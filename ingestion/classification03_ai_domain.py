"""Domain-oriented third AI source review for C03 label clashes and high-risk roles.

Selects 10 inter-AI disputes plus first-pass-vs-rule critical cases;
sends ONLY original source text to a fresh alternate-model session.
No human-gold or approved final labels are produced.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os

from .classification03 import OUT
from .classification03_ai import call_ai, validate_model_output
from .classification03_ai_second import read_items

ROOT=OUT/"ai-domain-third-v1"
VERSION="classification03-ai-domain-third-v1"

def source_candidates(root:Path=OUT)->list[dict]:
    original={p["posting_id"]:p for p in read_items(root/"reviewer-human.jsonl")}
    c2=set(json.loads((root/"ai-blind-second-v1"/"comparison.json").read_text(encoding="utf-8"))["disputed_ids"])
    triage=json.loads((root/"silver-human-triage-manifest.json").read_text(encoding="utf-8"))
    critical={row["posting_id"] for row in triage["selected"] if "CRITICAL_DISAGREEMENT" in row["reasons"]}
    ids=sorted(c2|critical)
    if not set(ids).issubset(original):raise ValueError("union cannot reference outside 69 locked source packets")
    if len(ids)!=12:
        raise ValueError(f"expected 12 unresolved union IDs, got {len(ids)}")
    return [original[id] for id in ids]

def run(root:Path=ROOT,model:str="opus")->dict:
    records=source_candidates()
    root.mkdir(parents=True,exist_ok=True)
    digest=sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()
    contract={"format":VERSION,"model":model,"source_payload_sha256":digest,
              "ids":[x["posting_id"] for x in records]}
    freeze=root/"contract.json"
    if freeze.exists() and json.loads(freeze.read_text(encoding="utf-8"))!=contract:
        raise ValueError("domain review input/model checkpoint differs")
    if not freeze.exists():freeze.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    assessed=[]
    new_cost=0
    for index in range(0,len(records),4):
        group=records[index:index+4]
        part=root/f"part-{index//4:02}.json"
        if part.exists():
            archive=json.loads(part.read_text(encoding="utf-8"))
            if archive.get("format")!=VERSION or archive["input_sha256"]!=sha256(json.dumps(group,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest():
                raise ValueError("third domain model part has mismatched frozen input")
            rows=validate_model_output(group,{"annotations":archive["annotations"]})
        else:
            rows,usage=call_ai(group,model,timeout=300)
            new_cost+=float(usage.get("cost_usd") or 0)
            archived={
                "format":VERSION,"model":model,"batch":index//4,
                "input_sha256":sha256(json.dumps(group,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest(),
                "created_utc":datetime.now(timezone.utc).isoformat(),
                "annotations":rows,"usage":usage,
            }
            temp=part.with_suffix(".json.tmp")
            temp.write_text(json.dumps(archived,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(temp,part)
        for row in rows:
            row["origin"]="DOMAIN_THIRD_AI_NOT_HUMAN"
            row["policy_version"]=VERSION
        assessed.extend(rows)
        print(json.dumps({"batch":index//4,"n":len(rows),"status":"PASS"},ensure_ascii=False),flush=True)
    assert len(assessed)==len(records)==12 and {r["posting_id"] for r in records}=={r["posting_id"] for r in assessed}
    final=root/"annotations.jsonl"
    temp=final.with_suffix(".jsonl.tmp")
    temp.write_text("".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in assessed),encoding="utf-8")
    os.replace(temp,final)
    summary={
        "checkpoint":"CLASSIFICATION-03-DOMAIN-THIRD-AI",
        "status":"AI_DOMAIN_REVIEW_COMPLETE_NOT_HUMAN_GOLD",
        "items":len(assessed),
        "selection":"10 inter-AI label conflicts union 6 critical rule-vs-AI differences",
        "status_counts":dict(Counter(r["label"] for r in assessed)),
        "model":model,"new_cost_usd":round(new_cost,3),
        "requires_real_human_adjudication":True,
    }
    (root/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

def summarize(root:Path=ROOT)->dict:
    items=source_candidates()
    ids={x["posting_id"] for x in items}
    a={x["posting_id"]:x for x in map(json.loads,(OUT/"ai-silver-v1"/"silver-annotations.jsonl").read_text(encoding="utf-8").splitlines()) if x["posting_id"] in ids}
    b={x["posting_id"]:x for x in map(json.loads,(OUT/"ai-blind-second-v1"/"annotations.jsonl").read_text(encoding="utf-8").splitlines()) if x["posting_id"] in ids}
    c={x["posting_id"]:x for x in map(json.loads,(root/"annotations.jsonl").read_text(encoding="utf-8").splitlines()) if x["posting_id"] in ids}
    if set(a)!=ids or set(b)!=ids or set(c)!=ids:
        raise ValueError("third model identity coverage incomplete")
    out=[]
    consensus=Counter()
    for row in items:
        id=row["posting_id"]
        all_labels=[a[id]["label"],b[id]["label"],c[id]["label"]]
        agreement=max(Counter(all_labels).values())
        consensus[f"{agreement}/3"]=consensus[f"{agreement}/3"]+1
        out.append({
            "posting_id":id,"title":row["title"],
            "review_a_ai":a[id]["label"],"review_b_ai":b[id]["label"],
            "domain_ai":c[id]["label"],"ai_agreement":agreement,
            "manual_adjudication_required":True
        })
    dest=root/"private-domain-disputes.json"
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={
        "checkpoint":"CLASSIFICATION-03-DOMAIN-THREE-AI-COMPARE",
        "status":"AI_DOMAIN_DISPUTES_TRIAGED_HUMAN_GOLD_BLOCKED",
        "reviewed":len(out),"ai_label_agreement_levels":dict(sorted(consensus.items())),
        "needs_manual_adjudication":len(out),
        "human_gold_unlocked":False,
        "disputed_ids":sorted(ids),
        "limitations":["Third model is an AI opinion, not an independent human domain reviewer.",
                       "Majority AI vote must not be auto-relabelled as independent gold."]
    }
    (root/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="opus")
    p.add_argument("--compare",action="store_true")
    args=p.parse_args()
    print(json.dumps(summarize() if args.compare else run(model=args.model),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
