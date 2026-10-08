"""CLASSIFICATION-03 archive expansion: AI-first-pass reviews for 309 unsampled IDs.

Creates independent silver sidecars; does not alter the 200-offer benchmark,
its blinded holdout, or the original 509/source C02 classifications.
"""
from __future__ import annotations
import argparse,json,os,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from threading import Event
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path

from .classification03 import load_verified_population,packet,OUT
from .classification03_ai import call_ai,validate_model_output
from .classification03_ai_delegate import rows_from
from .classification03_score import validate_one

ROOT=OUT/"ai-unsampled309-v1"
VERSION="classification03-ai-unsampled309-v1"
MODELS={"sonnet":"sonnet","opus":"opus"}
CHUNK=6
QUOTA_STOP=Event()

def sample():
    original,preclass=load_verified_population()
    selected={json.loads(line)["posting_id"] for line in (OUT/"reviewer-a.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    if len(selected)!=200 or not selected.issubset(original):
        raise ValueError("frozen 200 holdout is invalid")
    rest=[packet(original[id]) for id in sorted(set(original)-selected,key=lambda x:(int(x) if x.isdigit() else x))]
    if len(rest)!=309 or len({x["posting_id"] for x in rest})!=309:
        raise ValueError("expected exactly 309 complement source IDs")
    for row in rest:
        if set(row)!={"posting_id","revision_id","raw_payload_sha256","source","source_url","title","source_industry","description"}:
            raise ValueError("prediction/sampling field leaked into a source packet")
    return rest

def sha(obj):
    return sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def do_batch(index,items,dest,model):
    path=dest/"parts"/f"batch-{index:03}.json"
    source_hash=sha(items)
    if path.exists():
        old=json.loads(path.read_text(encoding="utf-8"))
        if old.get("format")!=VERSION or old.get("source_sha256")!=source_hash or old.get("model")!=model:
            raise ValueError("frozen 309 batch mismatch")
        validate_model_output(items,{"annotations":old["annotations"]})
        return {"batch":index,"status":"CACHED","n":len(items),"cost_usd":0}
    if QUOTA_STOP.is_set():
        return {"batch":index,"status":"BLOCKED_QUOTA","n":len(items),"reason":"provider session limit"}
    errs=[]
    for attempt in range(3):
        try:
            review,usage=call_ai(items,model,timeout=330)
            for x in review:
                x["origin"]="AI_ARCHIVE_309_SILVER_NOT_GOLD"
                x["policy_version"]=VERSION
            output={"format":VERSION,"model":model,"source_sha256":source_hash,
                    "created_utc":datetime.now(timezone.utc).isoformat(),
                    "annotations":review,"usage":usage}
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(tmp,path)
            return {"batch":index,"status":"PASS","n":len(items),"cost_usd":usage.get("cost_usd")}
        except Exception as exc:
            if "PROVIDER_QUOTA" in str(exc):
                QUOTA_STOP.set()
                return {"batch":index,"status":"BLOCKED_QUOTA","n":len(items),"reason":str(exc)[:160]}
            errs.append(f"{type(exc).__name__}: {str(exc)[:180]}")
            if attempt<2:time.sleep(1+attempt)
    return {"batch":index,"status":"FAILED","n":len(items),"errors":errs}

def stored_progress(items:list[dict],root:Path,model:str)->dict:
    """Read-only, source-verified progress; safe even when LLM quota is blocked."""
    dest=root/model
    contract_path=dest/"contract.json"
    if not contract_path.exists():
        return {"model":model,"expected":len(items),"assessed":0,
                "remaining":len(items),"cached_chunks":0,"chunks_total":(len(items)+CHUNK-1)//CHUNK,
                "label_counts":{},"next_missing_batch":0}
    contract=json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("format")!=VERSION or contract.get("model")!=model or contract.get("count")!=len(items) or contract.get("source_sha256")!=sha(items) or contract.get("source_ids")!=[r["posting_id"] for r in items]:
        raise ValueError("frozen archive source/model contract differs")
    completed=[];labels=Counter();missing=[];cached_chunks=0
    for i,start in enumerate(range(0,len(items),CHUNK)):
        chunk=items[start:start+CHUNK]
        part=dest/"parts"/f"batch-{i:03}.json"
        if not part.exists():
            missing.append(i)
            continue
        stored=json.loads(part.read_text(encoding="utf-8"))
        if stored.get("format")!=VERSION or stored.get("model")!=model or stored.get("source_sha256")!=sha(chunk):
            raise ValueError(f"cached batch {i} does not match frozen source")
        annotations=validate_model_output(chunk,{"annotations":stored["annotations"]})
        cached_chunks+=1
        completed.extend(annotations)
        labels.update(r["label"] for r in annotations)
    if len(completed)!=len({r["posting_id"] for r in completed}):
        raise ValueError("duplicate reviewed ID across cached batches")
    return {"model":model,"expected":len(items),
            "assessed":len(completed),"remaining":len(items)-len(completed),
            "cached_chunks":cached_chunks,
            "chunks_total":(len(items)+CHUNK-1)//CHUNK,
            "label_counts":dict(sorted(labels.items())),
            "next_missing_batch":missing[0] if missing else None}


def run(model:str="sonnet",workers:int=3,root:Path=ROOT):
    if model not in MODELS or workers<1 or workers>4:
        raise ValueError("invalid model/worker configuration")
    QUOTA_STOP.clear()
    items=sample()
    dest=root/model
    dest.mkdir(parents=True,exist_ok=True)
    contract={"format":VERSION,"model":model,"count":309,"chunk_size":CHUNK,
              "source_sha256":sha(items),"source_ids":[x["posting_id"] for x in items]}
    frozen=dest/"contract.json"
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8"))!=contract:
        raise ValueError("immutable 309 run contract changed")
    if not frozen.exists():frozen.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    groups=[items[i:i+CHUNK] for i in range(0,len(items),CHUNK)]
    states=[]
    with ThreadPoolExecutor(max_workers=workers) as e:
        jobs=[e.submit(do_batch,i,x,dest,model) for i,x in enumerate(groups)]
        for j in as_completed(jobs):
            done=j.result()
            states.append(done)
            print(json.dumps({"model":model,**done},ensure_ascii=False),flush=True)
    fails=[x for x in states if x["status"] not in ("PASS","CACHED")]
    assembled=[]
    if not fails:
        for i,chunk in enumerate(groups):
            stored=json.loads((dest/"parts"/f"batch-{i:03}.json").read_text(encoding="utf-8"))
            reviews=validate_model_output(chunk,{"annotations":stored["annotations"]})
            for x in reviews:
                x["origin"]="AI_ARCHIVE_309_SILVER_NOT_GOLD"
                x["policy_version"]=VERSION
            assembled.extend(reviews)
        if len(assembled)!=309 or {x["posting_id"] for x in assembled}!={x["posting_id"] for x in items}:
            raise ValueError("309 source identity reconciliation failed")
        tmp=dest/"annotations.jsonl.tmp"
        tmp.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in assembled),encoding="utf-8")
        os.replace(tmp,dest/"annotations.jsonl")
    progress=stored_progress(items,root,model)
    quota=[x for x in fails if x["status"]=="BLOCKED_QUOTA"]
    other_failures=[x for x in fails if x["status"]!="BLOCKED_QUOTA"]
    status={"status":("AI_ARCHIVE_309_COMPLETE" if progress["assessed"]==309 else
                      "AI_ARCHIVE_309_BLOCKED_QUOTA" if quota else "AI_ARCHIVE_309_INCOMPLETE"),
            "model":model,"expected":309,"assessed":progress["assessed"],
            "remaining":progress["remaining"],"cached_chunks":progress["cached_chunks"],
            "next_missing_batch":progress["next_missing_batch"],
            "newly_assessed":sum(x["n"] for x in states if x["status"]=="PASS"),
            "chunks":len(groups),"blocked_chunks":len(quota),"failed_chunks":other_failures,
            "counts":progress["label_counts"],
            "new_cost_usd":round(sum(float(x.get("cost_usd") or 0) for x in states),3),
            "origin":"AI_ONLY_SILVER_NOT_HUMAN_GOLD"}
    (dest/"summary.json").write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return status

def verified_opus_partial(root:Path,source_items:list[dict])->dict:
    """Use only completed Opus batches after provider quota failure; never invent missing votes."""
    from .classification03_ai import validate_model_output
    data={}
    folder=root/"opus"
    frozen=folder/"contract.json"
    if not frozen.exists():
        raise ValueError("Opus model checkpoint was not started")
    contract=json.loads(frozen.read_text(encoding="utf-8"))
    if contract.get("model")!="opus" or contract.get("source_sha256")!=sha(source_items) or contract.get("count")!=309:
        raise ValueError("Opus run contract not aligned with source snapshot")
    for index in range(0,len(source_items),CHUNK):
        chunk=source_items[index:index+CHUNK]
        path=folder/"parts"/f"batch-{index//CHUNK:03}.json"
        if not path.exists():
            continue
        stored=json.loads(path.read_text(encoding="utf-8"))
        if stored.get("format")!=VERSION or stored.get("model")!="opus" or stored.get("source_sha256")!=sha(chunk):
            raise ValueError(f"tampered Opus chunk: {index//CHUNK}")
        items=validate_model_output(chunk,{"annotations":stored["annotations"]})
        for row in items:
            id=row["posting_id"]
            if id in data:raise ValueError("duplicate Opus source ID")
            data[id]=row
    if not data or len(data)>309:
        raise ValueError("no verified source-bound Opus evidence")
    target=folder/"opus-partial-verified.jsonl"
    target.write_text("".join(json.dumps(data[id],ensure_ascii=False,sort_keys=True)+"\n" for id in sorted(data,key=int)),encoding="utf-8")
    return data


def merge(root:Path=ROOT,report:Path|None=Path("reports/classification-03/ai-archive509.json")):
    source,c02=load_verified_population()
    first200=rows_from(OUT/"ai-silver-v1"/"silver-annotations.jsonl")
    proposals200=rows_from(OUT/"ai-remaining153-v1"/"ai-proposals-200.jsonl")
    sonnet309=rows_from(root/"sonnet"/"annotations.jsonl")
    opus309=(rows_from(root/"opus"/"annotations.jsonl") if (root/"opus"/"annotations.jsonl").exists() else verified_opus_partial(root,sample()))
    if len(first200)!=200 or len(proposals200)!=200 or set(first200)!=set(proposals200) or len(sonnet309)!=309 or not (1<=len(opus309)<=309):
        raise ValueError("missing 509-archive evidence")
    if not set(opus309).issubset(sonnet309) or set(sonnet309)&set(first200) or set(sonnet309)|set(first200)!=set(source):
        raise ValueError("509 original archives and AI identities not reconciled")
    rows=[]
    counts=Counter();agree=Counter();risks=Counter()
    for id in sorted(source,key=int):
        record=packet(source[id])
        if id in first200:
            assessment=first200[id]
            extra=None
            origin="FROZEN_C03_SAMPLE_200"
            frozen=proposals200[id]
            if frozen["revision_id"]!=record["revision_id"] or frozen["raw_payload_sha256"]!=record["raw_payload_sha256"] or frozen["is_gold"] is not False:
                raise ValueError("200-proposal source hash/gold status mismatch")
            status=frozen["proposal"]
            votes=frozen["source_only_votes"]
        else:
            assessment=sonnet309[id]
            extra=opus309.get(id)
            origin="UNSAMPLED_309"
            votes={"first_sonnet":assessment["label"],"opus":extra["label"] if extra else None}
            status=(assessment["label"] if extra and assessment["label"]==extra["label"] and assessment["label"] in ("IT_TECHNICAL","NON_IT") else ("REVIEW_REQUIRED" if extra else "PENDING_SECOND_AI"))
        validate_one(assessment,record)
        if extra:validate_one(extra,record)
        counts[status]+=1
        if extra:
            agree["model_agreement" if assessment["label"]==extra["label"] else "model_disagreement"]+=1
        original=c02[id]["assessment"]["status"]
        if original=="IT_CONFIRMED" and status in ("NON_IT","REVIEW_REQUIRED"):risks["confident_it_conflict"]+=1
        if original=="NON_IT_CONFIRMED" and status in ("IT_TECHNICAL","REVIEW_REQUIRED"):risks["confident_non_it_conflict"]+=1
        rows.append({
            "posting_id":id,"revision_id":record["revision_id"],
            "raw_payload_sha256":record["raw_payload_sha256"],
            "source_panel":origin,"rule_status":original,
            "source_only_votes":votes,
            "proposed_silver_scope":status,
            "evidence_pointers":{"sonnet":("ai-silver-v1/silver-annotations.jsonl" if not extra else "ai-unsampled309-v1/sonnet/annotations.jsonl"),"opus":("ai-remaining153-v1/ai-proposals-200.jsonl" if not extra else "ai-unsampled309-v1/opus/annotations.jsonl")},
            "not_human_gold":True})
    folder=root/"merged"
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"ai-archive509-sidecar.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in rows),encoding="utf-8")
    result={"checkpoint":"CLASSIFICATION-03-AI-ARCHIVE509",
            "status":"AI_ARCHIVE509_TWO_MODEL_COMPLETE_HUMAN_GOLD_BLOCKED" if len(opus309)==309 else "AI_ARCHIVE509_FIRSTPASS_COMPLETE_SECOND_AI_QUOTA_BLOCKED",
            "source_total":509,"ai_first_review_coverage":509,
            "at_least_two_ai_reviews_coverage":200+len(opus309),
            "frozen_sample_200":200,"unsampled_extra_309":309,
            "opus_completed_309":len(opus309),
            "awaiting_second_ai_309":309-len(opus309),
            "extra_two_model_agreement_309":dict(sorted(agree.items())),
            "proposed_silver_scope_counts_509":dict(sorted(counts.items())),
            "conflicts_against_confident_rules":dict(sorted(risks.items())),
            "human_gold":0,"production_go":False,
            "caveat":"All 509 original IDs received at least one source-only AI review. The frozen 200 have three model opinions. For the other 309, missing Opus responses are explicitly marked PENDING_SECOND_AI due to provider session quota; they are not silently treated as review errors or consensus. No independent gold or production approval."}
    if report:
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",choices=tuple(MODELS),default="sonnet")
    p.add_argument("--workers",type=int,default=3)
    p.add_argument("--merge",action="store_true")
    p.add_argument("--status",action="store_true",help="Verify cached progress without calling AI")
    opts=p.parse_args()
    result=(merge() if opts.merge else stored_progress(sample(),ROOT,opts.model) if opts.status else run(opts.model,opts.workers))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
