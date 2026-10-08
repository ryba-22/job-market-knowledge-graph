"""CLASSIFICATION-03 remaining 153: second Sonnet and third Opus source-only reviews.

Immutable scope complement of existing 47 priority source IDs in frozen 200 sample.
Model assessments are silver-only; goldset and original C02 never modified.
"""
from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import argparse,json,os,time

from .classification03 import OUT
from .classification03_ai import call_ai,validate_model_output,FIELDS
from .classification03_ai_delegate import rows_from,source_population
from .classification03_score import validate_one

VERSION="classification03-ai-remaining153-v1"
ROOT=OUT/"ai-remaining153-v1"
SOURCE=OUT/"reviewer-a.jsonl"
PRIORITY=OUT/"reviewer-priority-human.jsonl"
BATCH_SIZE=6
MODELS={"second_sonnet":"sonnet","third_opus":"opus"}

def digest_file(path:Path)->str:
    return sha256(path.read_bytes()).hexdigest()

def canonical_sha(items):
    return sha256(json.dumps(items,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()

def remaining()->list[dict]:
    all_items=[json.loads(x) for x in SOURCE.read_text(encoding="utf-8").splitlines() if x.strip()]
    priority=[json.loads(x) for x in PRIORITY.read_text(encoding="utf-8").splitlines() if x.strip()]
    all_ids={r["posting_id"] for r in all_items}
    p_ids={r["posting_id"] for r in priority}
    if len(all_items)!=200 or len(all_ids)!=200 or len(priority)!=47 or len(p_ids)!=47 or not p_ids.issubset(all_ids):
        raise ValueError("original 200 / priority 47 frozen identities invalid")
    result=[item for item in all_items if item["posting_id"] not in p_ids]
    if len(result)!=153:
        raise ValueError("expected 153 remaining items")
    from .classification03 import load_verified_population
    rows,decisions=load_verified_population()
    for item in result:
        if set(item)!=set(FIELDS) or item["revision_id"]!=rows[item["posting_id"]]["revision_id"] or item["raw_payload_sha256"]!=rows[item["posting_id"]]["raw_payload_sha256"]:
            raise ValueError("source-only packet invalid or wrong revision")
    return result

def _batch(index:int,items:list[dict],folder:Path,model:str)->dict:
    path=folder/"parts"/f"part-{index:03}.json"
    chk=canonical_sha(items)
    if path.exists():
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("source_sha256")!=chk or data.get("model")!=model or data.get("version")!=VERSION:
            raise ValueError(f"cached batch {index} does not match frozen input")
        validate_model_output(items,{"annotations":data["annotations"]})
        return {"batch":index,"status":"CACHED","n":len(items),"cost_usd":0}
    errors=[]
    for attempt in range(3):
        try:
            outputs,usage=call_ai(items,model,timeout=330)
            for output in outputs:
                output["origin"]="C03_REMAINING_SOURCE_ONLY_AI_SILVER"
                output["policy_version"]=VERSION
            doc={"format":"classification03-source-only-review-batch-v1",
                 "version":VERSION,"model":model,"source_sha256":chk,
                 "annotations":outputs,"usage":usage,
                 "created_utc":datetime.now(timezone.utc).isoformat()}
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(tmp,path)
            return {"batch":index,"status":"PASS","n":len(items),"cost_usd":usage.get("cost_usd")}
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:180]}")
            if attempt<2:time.sleep(1+attempt)
    return {"batch":index,"status":"FAILED","n":len(items),"errors":errors}

def run_one(who:str,root:Path=ROOT,workers:int=3)->dict:
    if who not in MODELS or workers<1 or workers>4:raise ValueError("invalid reviewer configuration")
    items=remaining()
    model=MODELS[who]
    folder=root/who
    folder.mkdir(parents=True,exist_ok=True)
    contract={"format":VERSION,"model":model,"role":who,
              "full_source_sha256":digest_file(SOURCE),
              "priority_source_sha256":digest_file(PRIORITY),
              "sample_count":153,"batch_size":BATCH_SIZE,
              "ids":[r["posting_id"] for r in items]}
    frozen=folder/"contract.json"
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8"))!=contract:
        raise ValueError("locked input/reviewer contract differs")
    if not frozen.exists():frozen.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pieces=[items[i:i+BATCH_SIZE] for i in range(0,len(items),BATCH_SIZE)]
    states=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks=[pool.submit(_batch,i,chunk,folder,model) for i,chunk in enumerate(pieces)]
        for f in as_completed(tasks):
            state=f.result()
            states.append(state)
            print(json.dumps({"reviewer":who,**state},ensure_ascii=False),flush=True)
    problems=[s for s in states if s["status"]=="FAILED"]
    assembled=[]
    if not problems:
        for i,chunk in enumerate(pieces):
            data=json.loads((folder/"parts"/f"part-{i:03}.json").read_text(encoding="utf-8"))
            rows=validate_model_output(chunk,{"annotations":data["annotations"]})
            for row in rows:
                row["origin"]="C03_REMAINING_SOURCE_ONLY_AI_SILVER"
                row["policy_version"]=VERSION
            assembled.extend(rows)
        if len(assembled)!=153 or {r["posting_id"] for r in assembled}!={r["posting_id"] for r in items}:
            raise ValueError("missing/doubled source identities after rollup")
        dst=folder/"annotations.jsonl";tmp=dst.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in assembled),encoding="utf-8")
        os.replace(tmp,dst)
    result={"checkpoint":VERSION,
            "status":"AI_SILVER_REVIEW_PASS" if len(assembled)==153 else "AI_SILVER_REVIEW_INCOMPLETE",
            "reviewer":who,"model":model,"planned":153,"completed":len(assembled),
            "batches":len(pieces),"failed_batches":problems,
            "label_counts":dict(sorted(Counter(r["label"] for r in assembled).items())),
            "new_cost_usd":round(sum(float(s.get("cost_usd") or 0) for s in states),3),
            "source_only":True,"human_gold":False}
    (folder/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

def compare(root:Path=ROOT,public:Path|None=Path("reports/classification-03/ai-complete200.json"))->dict:
    items=remaining()
    rest={r["posting_id"] for r in items}
    original=rows_from(OUT/"ai-silver-v1"/"silver-annotations.jsonl")
    sonnet153=rows_from(root/"second_sonnet"/"annotations.jsonl")
    opus153=rows_from(root/"third_opus"/"annotations.jsonl")
    sonnet47=rows_from(OUT/"ai-blind-second-v1"/"annotations.jsonl")
    opus47=rows_from(OUT/"ai-delegation-v1"/"opus-47-annotations.jsonl")
    priority=[json.loads(s) for s in PRIORITY.read_text(encoding="utf-8").splitlines() if s]
    all_items=[json.loads(s) for s in SOURCE.read_text(encoding="utf-8").splitlines() if s]
    pids={r["posting_id"] for r in priority}
    sonnet47={id:assessment for id,assessment in sonnet47.items() if id in pids}
    if set(sonnet153)!=rest or set(opus153)!=rest or set(sonnet47)!=pids or set(opus47)!=pids:
        raise ValueError("200-benchmark reviewer identity coverage mismatch")
    second=sonnet153|sonnet47
    third=opus153|opus47
    if set(second)!=set(third) or set(second)!=set(original):raise ValueError("model identity mismatch")
    from .classification03 import load_verified_population
    archived,previous_rules=load_verified_population()
    votes=[]
    categories=Counter()
    disposition=Counter()
    unanimous=0
    all_agreement=Counter()
    disagreements=[]
    rule_conflicts=[]
    for row in all_items:
        id=row["posting_id"];set_votes=[original[id],second[id],third[id]]
        for assessment in set_votes:
            validate_one(assessment,row)
            if assessment["revision_id"]!=row["revision_id"] or assessment["raw_payload_sha256"]!=row["raw_payload_sha256"]:
                raise ValueError("source hash mismatch")
        labels=[r["label"] for r in set_votes]
        c=Counter(labels)
        most,n=c.most_common(1)[0]
        if n==3:unanimous+=1
        all_agreement[f"{n}_of_3"]+=1
        if n==1:
            cls="REVIEW_REQUIRED"
            status="NO_MAJORITY"
        elif most in ("IT_ADJACENT","UNDETERMINABLE"):
            cls="REVIEW_REQUIRED"
            status="AMBIGUOUS_SCOPE"
        else:
            cls=most
            status="UNANIMOUS" if n==3 else "AI_MAJORITY"
        categories[cls]+=1
        disposition[status]+=1
        prior=previous_rules[id]["assessment"]["status"]
        rule_conflict=(prior=="IT_CONFIRMED" and cls in ("NON_IT","REVIEW_REQUIRED")) or (prior=="NON_IT_CONFIRMED" and cls in ("IT_TECHNICAL","REVIEW_REQUIRED"))
        if rule_conflict: rule_conflicts.append(id)
        if n!=3 or cls=="REVIEW_REQUIRED":
            disagreements.append({"posting_id":id,"scope":cls,"reason":status,"first":labels[0],"second":labels[1],"third":labels[2]})
        votes.append({"posting_id":id,"revision_id":row["revision_id"],
                      "raw_payload_sha256":row["raw_payload_sha256"],
                      "source_only_votes":dict(zip(("first_sonnet","second_sonnet","third_opus"),labels)),
                      "proposal":cls,"disposition":status,"agreement":n,
                      "prior_rule_status":prior,"confident_rule_conflict":rule_conflict,
                      "source_grounded_evidence":[{"reviewer":name,"field":r["evidence_field"],"quote":r["quote"],"confidence":r["confidence"],"notes":r["notes"]} for name,r in zip(("first_sonnet","second_sonnet","third_opus"),set_votes)],
                      "is_gold":False})
    dest=root/"ai-proposals-200.jsonl"
    dest.write_text("".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in votes),encoding="utf-8")
    (root/"private-ai-disagreements.json").write_text(json.dumps(disagreements,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={"checkpoint":"CLASSIFICATION-03-ALL-200-AI-SILVER",
            "status":"THREE_AI_SILVER_200_COMPLETE_GOLD_BLOCKED",
            "source_postings":200,
            "first_ai_review":200,"second_ai_review":200,"third_ai_review":200,
            "new_second_reviews":153,"new_third_reviews":153,
            "unanimous_labels":unanimous,"agreement":dict(sorted(all_agreement.items())),
            "proposed_scope_counts":dict(sorted(categories.items())),
            "dispositions":dict(sorted(disposition.items())),
            "non_unanimous_or_review":len(disagreements),
            "confident_classifier_conflicts":len(rule_conflicts),
            "not_gold":True,"human_reviewed":0,
            "production_go":False,
            "limitations":["Both Sonnet sessions have correlated-model error risk",
                           "Opus is AI not independent human reviewer",
                           "Unanimity and 2/3 voting do not prove correctness",
                           "Intentionally enriched evaluation strata require weighting for any population estimate"]}
    if public:
        public.parent.mkdir(parents=True,exist_ok=True)
        public.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--reviewer",choices=["second_sonnet","third_opus"],default="second_sonnet")
    p.add_argument("--workers",type=int,default=3)
    p.add_argument("--compare",action="store_true")
    args=p.parse_args()
    result=compare() if args.compare else run_one(args.reviewer,workers=args.workers)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
if __name__=="__main__":main()
