"""CLASSIFICATION-03 AI first-pass: blind source-only silver review, never gold.

Runs Claude headlessly with no tools; logs per-batch verified outputs and failures.
No model predictions, source-stratum IDs or human-gold files are provided to LLM.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .classification03 import OUT
from .classification03_score import LABELS, VALID_FAMILIES, validate_one

VERSION = "classification03-ai-silver-v1"
SILVER = OUT / "ai-silver-v1"
BATCH_SIZE = 8
FIELDS = ["posting_id", "revision_id", "raw_payload_sha256", "source", "source_url", "title", "source_industry", "description"]
STRUCTURED_SCHEMA = {
    "type":"object",
    "properties":{
        "annotations":{"type":"array","items":{
            "type":"object","properties":{
                "posting_id":{"type":"string"},
                "label":{"type":"string","enum":sorted(LABELS)},
                "family":{"type":"string","enum":sorted(VALID_FAMILIES)},
                "evidence_field":{"type":"string","enum":["title","description","source_industry",""]},
                "quote":{"type":"string"},
                "notes":{"type":"string"},
                "confidence":{"type":"string","enum":["high","medium","low"]},
            },
            "required":["posting_id","label","family","evidence_field","quote","notes","confidence"],
            "additionalProperties":False
        }},
    },
    "required":["annotations"],
    "additionalProperties":False
}
PROMPT = """You are an AI job-scope annotator in a blind evaluation. Read each job posting's actual duties in full. You have NOT seen any classifier output or human review. Produce one decision per input ID. You are creating AI SILVER suggestions, NEVER ground truth.

STRICT scope:
IT_TECHNICAL = core employment duties involve developing/testing software, data systems, platform/cloud, IT infrastructure, network/system administration, cybersecurity engineering, ERP system configuration/integration, technical IT analysis/management. Mere company technology brand, IT sector, job title, use of software, AI-tool literacy, generic computer skills do NOT suffice.
NON_IT = work clearly lies outside technical IT: sales (even selling IT), marketing, teaching IT, logistics, administration, driver, industrial machine/CNC/robot programming for mechanical production, physically building telecom connections, office work. Use actual duties.
IT_ADJACENT = genuinely mixed roles or difficult scope boundary: physical electronics repair, industrial PLC/embedded automation, IT presales plus engineering, content-commerce plus web development, infosec governance/compliance without technical operations, etc.
UNDETERMINABLE = insufficient reliable source duties or contradictory incomplete offer.
Use a specific job family from the supplied allowed enum. Review source text only; do not assume fresh/active status.
For every IT_TECHNICAL label, evidence_field MUST be description; for every NON_IT prefer description; quote must be an EXACT, CONTIGUOUS, verbatim substring from the chosen source field, 5-220 characters, no paraphrases or omitted text. Ensure quoted source supports the label. If a relevant source quote cannot be provided, use UNDETERMINABLE or IT_ADJACENT and explain.
For IT_ADJACENT/UNDETERMINABLE notes >= 12 characters in English or Polish explaining the reason. For IT or non-IT notes can be a short factual basis.
Do not invent source facts, omit IDs, or refer to other evaluations.
Input: an array of eight or fewer source-only JobPosting packets.
Return ONLY structured JSON with annotations in the same order, one per input posting_id.
"""

def load_packets(source: Path = OUT / "reviewer-a.jsonl") -> list[dict]:
    packets=[json.loads(s) for s in source.read_text(encoding="utf-8").splitlines() if s.strip()]
    if len(packets)!=200 or len({r["posting_id"] for r in packets})!=200:
        raise ValueError("AI silver requires exact frozen 200-packet population")
    if not all(set(r)==set(FIELDS) for r in packets):
        raise ValueError("blind source packet contains unexpected fields, abort")
    return packets


def validate_model_output(items: list[dict], incoming: dict) -> list[dict]:
    rows = incoming.get("annotations")
    if not isinstance(rows,list) or len(rows)!=len(items):
        raise ValueError("model output skipped/added an item")
    byid={r["posting_id"]:r for r in items}
    if len({x["posting_id"] for x in rows}) != len(items) or set(x["posting_id"] for x in rows)!=set(byid):
        raise ValueError("model output identities mismatch source")
    verified=[]
    for item in rows:
        if item.get("confidence") not in ("high","medium","low"):
            raise ValueError("missing confidence")
        original=byid[item["posting_id"]]
        extended={
            "posting_id":item["posting_id"],
            "revision_id":original["revision_id"],
            "raw_payload_sha256":original["raw_payload_sha256"],
            "label":item["label"],"family":item["family"],
            "evidence_field":item["evidence_field"],"quote":item["quote"],
            "notes":item["notes"],"confidence":item["confidence"],
            "origin":"AI_SILVER_NOT_HUMAN_GOLD",
            "policy_version":VERSION
        }
        validate_one(extended,original)
        verified.append(extended)
    return verified


def call_ai(items: list[dict], model: str, timeout: int = 220) -> tuple[list[dict], dict]:
    prompt=PROMPT+"\nSOURCE-ONLY PACKETS:\n"+json.dumps(items,ensure_ascii=False)
    args=["claude","-p","--restricted","--tools","","--model",model,
          "--max-turns","1","--output-format","json",
          "--json-schema",json.dumps(STRUCTURED_SCHEMA,separators=(",",":"))]
    process=subprocess.run(args,input=prompt,capture_output=True,text=True,timeout=timeout,cwd="/tmp")
    if process.returncode:
        try:
            provider_response=json.loads(process.stdout or "{}")
            provider_detail=str(provider_response.get("result") or "")[:200]
        except json.JSONDecodeError:
            provider_detail=""
        if "session limit" in provider_detail.lower() or "usage limit" in provider_detail.lower():
            raise RuntimeError(f"PROVIDER_QUOTA: {provider_detail}")
        raise RuntimeError(f"LLM failed: exit {process.returncode}, provider: {provider_detail[:100]}, stderr: {(process.stderr or '')[:120]}")
    answer=json.loads(process.stdout)
    if answer.get("is_error"):
        raise RuntimeError(f"LLM returned error {str(answer.get('result'))[:220]}")
    structured=answer.get("structured_output")
    if not isinstance(structured,dict):
        raise RuntimeError("Missing validated structured output")
    result=validate_model_output(items,structured)
    usage={"model":model,"cost_usd":answer.get("total_cost_usd"),
           "duration_ms":answer.get("duration_ms"),
           "usage":answer.get("usage"),"n":len(items)}
    return result,usage


def process_batch(batch_index: int, items: list[dict], root: Path, model: str) -> dict:
    part=root/"parts"/f"part-{batch_index:03d}.json"
    source_sha=sha256(json.dumps(items,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if part.exists():
        document=json.loads(part.read_text(encoding="utf-8"))
        if document.get("source_sha256")!=source_sha or document.get("policy_version")!=VERSION or document.get("model")!=model:
            raise ValueError(f"frozen batch config differs: {batch_index}")
        validate_model_output(items,{"annotations":document["annotations"]})
        return {"batch":batch_index,"status":"CACHED","n":len(items),"cost_usd":0}
    issues=[]
    for attempt in range(1,4):
        try:
            output,usage=call_ai(items,model)
            meta={"format":"classification03-ai-silver-part-v1","policy_version":VERSION,
                  "model":model,"source_sha256":source_sha,"batch":batch_index,
                  "created_at":datetime.now(timezone.utc).isoformat(),
                  "annotations":output,"usage":usage}
            part.parent.mkdir(parents=True,exist_ok=True)
            path=part.with_suffix(".json.tmp")
            path.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(path,part)
            return {"batch":batch_index,"status":"PASS","n":len(items),"cost_usd":usage["cost_usd"]}
        except (RuntimeError,ValueError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
            issues.append(str(exc)[:240])
            if attempt<3:time.sleep(1.5*attempt)
    return {"batch":batch_index,"status":"FAILED","n":len(items),"issues":issues}


def run(output: Path=SILVER,model: str="sonnet",workers: int=2) -> dict:
    packets=load_packets()
    if workers<1 or workers>4:
        raise ValueError("1-4 workers supported")
    output.mkdir(parents=True,exist_ok=True)
    manifest=output/"run-contract.json"
    source_sha=sha256((OUT/"reviewer-a.jsonl").read_bytes()).hexdigest()
    contract={"format":"classification03-ai-silver-run-v1","version":VERSION,
              "model":model,"source_sha256":source_sha,"count":len(packets),
              "batch_size":BATCH_SIZE,"schema_sha256":sha256(json.dumps(STRUCTURED_SCHEMA,sort_keys=True).encode()).hexdigest()}
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))!=contract:
        raise ValueError("existing silver run has a DIFFERENT frozen contract")
    if not manifest.exists():
        manifest.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    groups=[packets[i:i+BATCH_SIZE] for i in range(0,len(packets),BATCH_SIZE)]
    results=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures={ex.submit(process_batch,index,items,output,model):index for index,items in enumerate(groups)}
        for future in as_completed(futures):
            status=future.result()
            results.append(status)
            print(json.dumps(status,ensure_ascii=False),flush=True)
    succeeded=sorted((r["batch"] for r in results if r["status"] in ("PASS","CACHED")))
    failures=[r for r in results if r["status"]=="FAILED"]
    all_rows=[]
    if not failures and len(succeeded)==len(groups):
        for ix, items in enumerate(groups):
            part=json.loads((output/"parts"/f"part-{ix:03d}.json").read_text(encoding="utf-8"))
            all_rows.extend(validate_model_output(items,{"annotations":part["annotations"]}))
        if len(all_rows)!=len(packets) or len({a["posting_id"] for a in all_rows})!=len(packets):
            raise ValueError("silver rollup not one-to-one with original source packets")
        merged=output/"silver-annotations.jsonl"
        temp=merged.with_suffix(".jsonl.tmp")
        temp.write_text("".join(json.dumps(a,ensure_ascii=False,sort_keys=True)+"\n" for a in all_rows),encoding="utf-8")
        os.replace(temp,merged)
    counts=Counter(x["label"] for x in all_rows)
    overview={
        "checkpoint":"CLASSIFICATION-03-AI-FIRSTPASS",
        "status":"SILVER_COMPLETE_HUMAN_GOLD_STILL_BLOCKED" if len(all_rows)==200 else "SILVER_INCOMPLETE",
        "model":model,"source_postings":len(packets),"ai_silver_annotations":len(all_rows),
        "label_counts":dict(sorted(counts.items())),"batch_count":len(groups),
        "batches_complete":len(succeeded),"batches_failed":failures,
        "new_cost_usd":round(sum(float(x.get("cost_usd") or 0) for x in results),3),
        "no_independent_gold":True,
        "human_review_required":True,
    }
    (output/"summary.json").write_text(json.dumps(overview,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return overview


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=SILVER)
    p.add_argument("--model",default="sonnet")
    p.add_argument("--workers",type=int,default=2)
    args=p.parse_args()
    print(json.dumps(run(args.out,args.model,args.workers),ensure_ascii=False,indent=2),flush=True)


if __name__=="__main__":
    main()
