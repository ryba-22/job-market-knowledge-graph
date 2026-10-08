"""CLASSIFICATION-03 AI delegation: third blind source-only review on all 47 cases.

Existing 12 Opus source-only adjudications are reused, 35 missing cases are
reviewed in fresh Opus sessions, and three AI labels are reconciled as SILVER.
No human labels, no goldset mutation, no source data changes.
"""
from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from hashlib import sha256
import json,os,time,argparse
from pathlib import Path

from .classification03 import OUT,load_verified_population
from .classification03_ai import call_ai,validate_model_output
from .classification03_ai_second import read_items

VERSION="classification03-ai-delegation-v1"
OUT_ROOT=OUT/"ai-delegation-v1"
PRIORITY=OUT/"reviewer-priority-human.jsonl"
PREVIOUS_DOMAIN=OUT/"ai-domain-third-v1/annotations.jsonl"
MODEL="opus"
BATCH_SIZE=5

def rows_from(path:Path)->dict:
    rows=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({item["posting_id"] for item in rows})!=len(rows):
        raise ValueError(f"duplicated IDs: {path}")
    return {item["posting_id"]:item for item in rows}

def source_population()->tuple[list[dict],dict,dict]:
    records=[json.loads(line) for line in PRIORITY.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records)!=47 or len({r["posting_id"] for r in records})!=47:
        raise ValueError("expected locked 47 blind source-only cases")
    original,baseline=load_verified_population()
    for record in records:
        id=record["posting_id"]
        if id not in original or record["raw_payload_sha256"]!=original[id]["raw_payload_sha256"] or record["revision_id"]!=original[id]["revision_id"]:
            raise ValueError(f"source revision changed: {id}")
        if set(record)!={"posting_id","source","source_url","title","description","source_industry","revision_id","raw_payload_sha256"}:
            raise ValueError("blind source packet contains an unexpected field")
    earlier=rows_from(PREVIOUS_DOMAIN)
    if not set(earlier).issubset({r["posting_id"] for r in records}) or len(earlier)!=12:
        raise ValueError("existing third reviewer source cohort changed")
    for record in records:
        id=record["posting_id"]
        if id in earlier:
            validate_model_output([record],{"annotations":[earlier[id]]})
            if earlier[id].get("origin")!="DOMAIN_THIRD_AI_NOT_HUMAN":
                raise ValueError("existing domain AI provenance not recognized")
    return records, earlier, baseline

def locked_sha(items:list[dict])->str:
    return sha256(json.dumps(items,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()

def one_batch(index:int,items:list[dict],dest:Path,model:str)->dict:
    path=dest/"parts"/f"part-{index:02}.json"
    input_hash=locked_sha(items)
    if path.exists():
        v=json.loads(path.read_text(encoding="utf-8"))
        if v.get("input_sha256")!=input_hash or v.get("version")!=VERSION or v.get("model")!=model:
            raise ValueError("existing part differs from frozen contract")
        validate_model_output(items,{"annotations":v["annotations"]})
        return {"index":index,"status":"CACHED","n":len(items),"cost_usd":0}
    errors=[]
    for trial in range(3):
        try:
            output,usage=call_ai(items,model,timeout=330)
            doc={
                "format":"classification03-opus-source-review-part-v1",
                "version":VERSION,"model":model,"input_sha256":input_hash,
                "created_utc":datetime.now(timezone.utc).isoformat(),
                "annotations":output,"usage":usage,
            }
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(temp,path)
            return {"index":index,"status":"PASS","n":len(items),"cost_usd":usage["cost_usd"]}
        except Exception as err:
            errors.append(f"{type(err).__name__}: {str(err)[:180]}")
            if trial<2:time.sleep(trial+1)
    return {"index":index,"status":"FAILED","n":len(items),"errors":errors}

def run(dest:Path=OUT_ROOT,model:str=MODEL,workers:int=3)->dict:
    if not 1<=workers<=4:raise ValueError("workers outside 1..4")
    source,earlier,baseline=source_population()
    remaining=[r for r in source if r["posting_id"] not in earlier]
    if len(remaining)!=35:raise ValueError("must have 35 new cases")
    dest.mkdir(parents=True,exist_ok=True)
    contract={
        "format":VERSION,"model":model,
        "source_packet_sha256":sha256(PRIORITY.read_bytes()).hexdigest(),
        "existing_domain_sha256":sha256(PREVIOUS_DOMAIN.read_bytes()).hexdigest(),
        "missing_identities":[r["posting_id"] for r in remaining],
        "batch_size":BATCH_SIZE,
    }
    freeze=dest/"run-contract.json"
    if freeze.exists() and json.loads(freeze.read_text(encoding="utf-8"))!=contract:
        raise ValueError("frozen delegation contract changed")
    if not freeze.exists():freeze.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    chunks=[remaining[i:i+BATCH_SIZE] for i in range(0,len(remaining),BATCH_SIZE)]
    stats=[]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks=[executor.submit(one_batch,i,chunk,dest,model) for i,chunk in enumerate(chunks)]
        for task in as_completed(tasks):
            result=task.result()
            stats.append(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
    failed=[s for s in stats if s["status"]=="FAILED"]
    opus=dict(earlier)
    if not failed:
        for i,chunk in enumerate(chunks):
            doc=json.loads((dest/"parts"/f"part-{i:02}.json").read_text(encoding="utf-8"))
            for r in validate_model_output(chunk,{"annotations":doc["annotations"]}):
                r["origin"]="THIRD_AI_OPUS_SOURCE_ONLY_NOT_HUMAN"
                r["policy_version"]=VERSION
                opus[r["posting_id"]]=r
        if set(opus)!={r["posting_id"] for r in source}:
            raise ValueError("third reviewer does not cover exactly 47 source IDs")
        target=dest/"opus-47-annotations.jsonl"
        tmp=target.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(opus[r["posting_id"]],ensure_ascii=False,sort_keys=True)+"\n" for r in source),encoding="utf-8")
        os.replace(tmp,target)
    summary={
        "checkpoint":"CLASSIFICATION-03-DELEGATED-THIRD-AI",
        "status":"AI_47_COMPLETE_GOLD_STILL_BLOCKED" if len(opus)==47 else "AI_47_INCOMPLETE",
        "source_47":47,"previous_opus_reused":len(earlier),"new_opus_expected":35,
        "opus_reviewed":len(opus),
        "batches_total":len(chunks),"failed_batches":failed,
        "new_cost_usd":round(sum(float(s.get("cost_usd") or 0) for s in stats),3),
        "model":model,
        "independent_human_reviews":0,
        "never_a_human_goldset":True,
    }
    (dest/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

def reconcile(dest:Path=OUT_ROOT, report:Path|None=Path("reports/classification-03/ai-delegated-47.json"))->dict:
    source,earlier,c02=source_population()
    third=rows_from(dest/"opus-47-annotations.jsonl")
    first=rows_from(OUT/"ai-silver-v1"/"silver-annotations.jsonl")
    second=rows_from(OUT/"ai-blind-second-v1"/"annotations.jsonl")
    expected={r["posting_id"] for r in source}
    if set(third)!=expected or not expected.issubset(first) or not expected.issubset(second):
        raise ValueError("three-reviewer coverage mismatch")
    annotations=[]
    counts=Counter()
    unanimity=Counter()
    failures=Counter()
    for src in source:
        id=src["posting_id"]
        votes=[first[id],second[id],third[id]]
        for v in votes:validate_model_output([src],{"annotations":[v]})
        distribution=Counter(v["label"] for v in votes)
        winner,n=max(distribution.items(),key=lambda x:(x[1],x[0]))
        if n==1:
            disposition="AI_DISPUTE_NO_MAJORITY"
            suggested="REVIEW_REQUIRED"
        elif winner in ("IT_ADJACENT","UNDETERMINABLE"):
            disposition="AI_AGREE_OUTSIDE_BINARY_SCOPE"
            suggested="REVIEW_REQUIRED"
        else:
            disposition="AI_UNANIMOUS_SILVER" if n==3 else "AI_MAJORITY_SILVER_UNVERIFIED"
            suggested=winner
        original_rules=c02[id]["assessment"]["status"]
        issue=original_rules=="IT_CONFIRMED" and suggested in ("NON_IT","REVIEW_REQUIRED") or original_rules=="NON_IT_CONFIRMED" and suggested in ("IT_TECHNICAL","REVIEW_REQUIRED")
        if issue:failures["conflicts_with_confident_rule"]+=1
        counts[suggested]+=1
        unanimity[disposition]+=1
        annotations.append({
            "posting_id":id,"revision_id":src["revision_id"],
            "raw_payload_sha256":src["raw_payload_sha256"],
            "proposed_silver_scope":suggested,"disposition":disposition,
            "ai_votes":{ "first_sonnet":first[id]["label"],
                        "second_sonnet":second[id]["label"],
                        "third_opus":third[id]["label"] },
            "vote_agreement":n,
            "source_grounded_evidence":[
                {"reviewer":label,"field":v["evidence_field"],"quote":v["quote"],
                 "notes":v["notes"],"confidence":v["confidence"]}
                 for label,v in zip(["first_sonnet","second_sonnet","third_opus"],votes)
            ],
            "prior_rule_status":original_rules,
            "high_risk_rule_disagreement":bool(issue),
            "is_human_gold":False,
        })
    data=dest/"ai-silver-proposals.jsonl"
    data.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in annotations),encoding="utf-8")
    summary={
        "checkpoint":"CLASSIFICATION-03-THREE-AI-CONSENSUS-47",
        "status":"THREE_AI_SILVER_RECONCILED_HUMAN_GOLD_STILL_BLOCKED",
        "source_reviewed":len(annotations),"gold_labels":0,
        "proposed_silver_scope_counts":dict(sorted(counts.items())),
        "disposition_counts":dict(sorted(unanimity.items())),
        "conflicts_with_confident_rules":failures["conflicts_with_confident_rule"],
        "models":"Sonnet first + separate Sonnet second + Opus source-only (reused 12 + new 35)",
        "majority_is_not_accuracy":True,
        "risks":["Correlated errors in two Sonnet runs, even with distinct sessions",
                 "Three-way agreement does not establish human truth",
                 "Strict human-gold quality gate remains blocked",
                 "Source selection enriched for risk; counts are not market estimates"],
        "proposal_path":str(data),
        "production_go":False,
    }
    if report:
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--reconcile",action="store_true")
    parser.add_argument("--workers",type=int,default=3)
    args=parser.parse_args()
    print(json.dumps(reconcile() if args.reconcile else run(workers=args.workers),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
