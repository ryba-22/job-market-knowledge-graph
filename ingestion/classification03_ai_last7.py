"""Fourth AI opinion on seven persistent out-of-scope/insufficient-source offers.

This is a source-only *challenge* review, not a forced binary conversion.
It does not change the existing original 47 silver sidecar or any gold labels.
"""
from __future__ import annotations
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
import argparse

from .classification03 import OUT
from .classification03_ai import call_ai,validate_model_output
from .classification03_ai_delegate import rows_from

ROOT=OUT/"ai-last7-challenge-v1"
VERSION="classification03-ai-last7-challenge-v1"

def cohort():
    proposals=rows_from(OUT/"ai-delegation-v1"/"ai-silver-proposals.jsonl")
    pending={id for id,row in proposals.items() if row["proposed_silver_scope"]=="REVIEW_REQUIRED"}
    original=rows_from(OUT/"reviewer-priority-human.jsonl")
    if len(pending)!=7 or not pending.issubset(original):
        raise ValueError("last-seven cohort differs from prior frozen proposal")
    return [original[id] for id in sorted(pending)]

def review(root=ROOT):
    items=cohort()
    root.mkdir(parents=True,exist_ok=True)
    original_sha=sha256(json.dumps(items,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    contract={"format":VERSION,"ids":[x["posting_id"] for x in items],
              "source_sha256":original_sha,"model":"opus"}
    freeze=root/"contract.json"
    if freeze.exists() and json.loads(freeze.read_text(encoding="utf-8"))!=contract:
        raise ValueError("frozen unresolved-seven cohort changed")
    if not freeze.exists():freeze.write_text(json.dumps(contract,indent=2)+"\n")
    path=root/"annotations.jsonl"
    if path.exists():
        rows=rows_from(path)
        if set(rows)!={x["posting_id"] for x in items}:
            raise ValueError("cached unresolved-review identities mismatch")
        validated=validate_model_output(items,{"annotations":list(rows.values())})
    else:
        validated,usage=call_ai(items,"opus",timeout=300)
        for item in validated:
            item["origin"]="FOURTH_AI_SOURCE_ONLY_SILVER_NOT_HUMAN"
            item["policy_version"]=VERSION
        path.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in validated))
        (root/"usage.json").write_text(json.dumps(usage,ensure_ascii=False,indent=2)+"\n")
    tally=Counter(r["label"] for r in validated)
    summary={"checkpoint":VERSION,"status":"FOURTH_AI_LAST7_COMPLETE_SILVER_ONLY",
             "source_reviewed":len(validated),"label_counts":dict(sorted(tally.items())),
             "old_pending_count":7,"gold_labels":0,"mutated_existing_proposals":False}
    (root/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    return summary

def main():
    print(json.dumps(review(),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
