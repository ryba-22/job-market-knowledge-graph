"""Second blind AI review of C03's existing 69-item human triage packet.

Separate stateless LLM calls, no earlier AI/classifier labels. Output is
AI-to-AI agreement and domain-dispute queue, NOT independent human gold.
"""
from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import argparse,json,os,time

from .classification03 import OUT
from .classification03_ai import call_ai,validate_model_output,load_packets,FIELDS
from .classification03_score import validate_one

VERSION="classification03-second-blind-ai-v1"
OUT_ROOT=OUT/"ai-blind-second-v1"
PACKET=OUT/"reviewer-human.jsonl"
BATCH_SIZE=6

def read_items(path:Path=PACKET)->list[dict]:
    items=[json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
    if len(items)!=69 or len({x["posting_id"] for x in items})!=69:
        raise ValueError("second pass requires the locked 69-offer triage cohort")
    if not all(set(x)==set(FIELDS) for x in items):
        raise ValueError("packet contains non-source fields; refusal protects blinding")
    return items

def checksum(obj):
    return sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def batch_run(index:int,items:list[dict],root:Path,model:str)->dict:
    dest=root/"parts"/f"part-{index:03}.json"
    src_hash=checksum(items)
    if dest.exists():
        saved=json.loads(dest.read_text(encoding="utf-8"))
        if saved.get("source_sha256")!=src_hash or saved.get("model")!=model or saved.get("version")!=VERSION:
            raise ValueError(f"immutable AI second reviewer batch mismatch: {index}")
        validate_model_output(items,{"annotations":saved["annotations"]})
        return {"batch":index,"status":"CACHED","n":len(items),"cost_usd":0}
    errors=[]
    for attempt in range(3):
        try:
            labeled,usage=call_ai(items,model=model,timeout=240)
            for x in labeled:
                x["origin"]="SECOND_BLIND_AI_NOT_HUMAN_GOLD"
                x["policy_version"]=VERSION
            obj={
                "format":"classification03-ai-blind-second-part-v1",
                "source_sha256":src_hash,
                "version":VERSION,"model":model,"index":index,
                "annotations":labeled,"usage":usage,
                "created_utc":datetime.now(timezone.utc).isoformat(),
            }
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_suffix(".json.tmp")
            temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(temp,dest)
            return {"batch":index,"status":"PASS","n":len(items),"cost_usd":usage["cost_usd"]}
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:190]}")
            if attempt<2:time.sleep(attempt+1)
    return {"batch":index,"status":"FAILED","n":len(items),"errors":errors}

def run(root:Path=OUT_ROOT,model:str="sonnet",workers:int=3)->dict:
    items=read_items()
    if workers not in (1,2,3,4): raise ValueError("workers must be between 1 and 4")
    src_sha=sha256(PACKET.read_bytes()).hexdigest()
    run_contract={
        "format":"classification03-second-blind-ai-run-v1",
        "version":VERSION,"source_packet_sha256":src_sha,
        "count":69,"batch_size":BATCH_SIZE,"model":model
    }
    root.mkdir(parents=True,exist_ok=True)
    frozen=root/"run-contract.json"
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8"))!=run_contract:
        raise ValueError("frozen run contract differs")
    if not frozen.exists():frozen.write_text(json.dumps(run_contract,indent=2)+"\n")
    batches=[items[i:i+BATCH_SIZE] for i in range(0,len(items),BATCH_SIZE)]
    statuses=[]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures=[executor.submit(batch_run,i,b,root,model) for i,b in enumerate(batches)]
        for f in as_completed(futures):
            st=f.result()
            statuses.append(st)
            print(json.dumps(st,ensure_ascii=False),flush=True)
    failures=[s for s in statuses if s["status"]=="FAILED"]
    assembled=[]
    if not failures:
        for i,batch in enumerate(batches):
            part=json.loads((root/"parts"/f"part-{i:03}.json").read_text(encoding="utf-8"))
            rows=validate_model_output(batch,{"annotations":part["annotations"]})
            for row in rows:
                row["origin"]="SECOND_BLIND_AI_NOT_HUMAN_GOLD"
                row["policy_version"]=VERSION
            assembled.extend(rows)
        if len(assembled)!=69 or set(x["posting_id"] for x in assembled)!=set(x["posting_id"] for x in items):
            raise ValueError("second blind pass not reconciled to 69-source cohort")
        fn=root/"annotations.jsonl"
        tmp=fn.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in assembled),encoding="utf-8")
        os.replace(tmp,fn)
    summary={
        "checkpoint":"CLASSIFICATION-03-AI-SECOND-BLIND",
        "status":"SECOND_AI_PASS_COMPLETE_HUMAN_GOLD_STILL_BLOCKED" if len(assembled)==69 else "SECOND_AI_PASS_INCOMPLETE",
        "source_offer_count":69,
        "assessed":len(assembled),"status_counts":dict(Counter(x["label"] for x in assembled)),
        "batches":len(batches),"batch_failures":failures,
        "model":model,
        "cost_usd_this_run":round(sum(float(s.get("cost_usd") or 0) for s in statuses),3),
        "source_packet_sha256":src_sha,
        "not_independent_human_review":True,
        "no_goldset_unlocked":True,
    }
    (root/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary

def compare(root:Path=OUT_ROOT)->dict:
    first=OUT/"ai-silver-v1"/"silver-annotations.jsonl"
    second=root/"annotations.jsonl"
    if not second.exists():
        return {"status":"BLOCKED_SECOND_REVIEW_INCOMPLETE"}
    p={x["posting_id"]:x for x in map(json.loads,first.read_text(encoding="utf-8").splitlines())}
    q={x["posting_id"]:x for x in map(json.loads,second.read_text(encoding="utf-8").splitlines())}
    packet={x["posting_id"]:x for x in read_items()}
    if set(q)!=set(packet) or not set(q).issubset(p):
        raise ValueError("cross-review identity mismatch")
    same,disputes=0,[]
    by=Counter()
    confidence=Counter()
    for id in sorted(q):
        a,b=p[id],q[id]
        validate_one(a,packet[id]);validate_one(b,packet[id])
        by[f'{a["label"]} -> {b["label"]}']+=1
        confidence[f'{a["confidence"]} -> {b["confidence"]}']+=1
        if a["label"]==b["label"]:same+=1
        else:
            disputes.append({
                "posting_id":id,"first_ai_label":a["label"],
                "second_ai_label":b["label"],
                "first_confidence":a["confidence"],
                "second_confidence":b["confidence"],
                "source_revision_id":packet[id]["revision_id"],
                "source_payload_sha256":packet[id]["raw_payload_sha256"]
            })
    # Keep model decisions separate from blinded source-only task packets.
    dispute_path=root/"private-ai-disputes.json"
    dispute_path.write_text(json.dumps(disputes,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={
        "checkpoint":"CLASSIFICATION-03-AI-SECOND-BLIND-COMPARE",
        "status":"AI_CONSENSUS_RECORDED_HUMAN_REVIEW_STILL_REQUIRED",
        "compared":len(q),"same_scope_label":same,"different_scope_label":len(disputes),
        "cross_model_agreement_not_accuracy":round(same/len(q),4),
        "confusion_counts":dict(sorted(by.items())),
        "reviewer_confidence_pairs":dict(sorted(confidence.items())),
        "disputed_ids":sorted(x["posting_id"] for x in disputes),
        "unreviewed_human_label_count":69,
        "independent_human_gold":0,
        "release_gate":"BLOCKED",
        "limitations":["Two independent LLM invocations do not establish independent human annotation.",
                       "A and B can make correlated errors; agreement is not validation.",
                       "The enriched 69-offer queue is not an unbiased representative survey."],
    }
    (root/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="sonnet")
    p.add_argument("--workers",type=int,default=3)
    p.add_argument("--compare",action="store_true")
    args=p.parse_args()
    print(json.dumps(compare() if args.compare else run(model=args.model,workers=args.workers),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
