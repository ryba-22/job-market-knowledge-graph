#!/usr/bin/env python3
"""RI-01 triage of unverified model drafts against existing extractor proposals.

This produces an actionable issue queue, NEVER fabricated human-gold labels.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/".local-evidence/ri01/ai-review"
ORIG=ROOT/".local-evidence/ri01"


def main():
    drafts_file=WORK/"ai-firstpass.jsonl"
    if not drafts_file.exists():
        raise SystemExit("Missing model draft output")
    drafts=[json.loads(x) for x in drafts_file.open(encoding="utf-8")]
    base=defaultdict(list)
    for line in (ORIG/"assertion-candidates.jsonl").open(encoding="utf-8"):
        item=json.loads(line)
        base[item["posting_id"]].append(item)
    packets={item["posting_id"]:item for item in map(json.loads,(ORIG/"review-packets.jsonl").open(encoding="utf-8"))}
    issues=[]
    by_posting=defaultdict(Counter)
    for item in drafts:
        postid=item["posting_id"]
        if postid not in packets or packets[postid]["split"]!="development":
            raise SystemExit("HOLDOUT_LEAKAGE_OR_UNKNOWN_POSTING:"+postid)
        found=base[postid]
        quote=item["quote"].strip()
        match=[a for a in found if a["quote"].strip()==quote]
        fuzzy=[a for a in found if quote in a["quote"] or a["quote"] in quote]
        kind=item["kind_draft"]
        reasons=[]
        if not item["source_exact"]:
            reasons.append("SOURCE_QUOTE_NOT_EXACT")
        if match:
            observed={a["modality_candidate"] for a in match}
            if kind not in observed and kind!="UNKNOWN":
                reasons.append("DIRECT_LABEL_CONFLICT")
            if "MUST" in observed and kind=="NICE":
                reasons.append("MUST_VS_NICE_CRITICAL")
            if "NICE" in observed and kind=="MUST":
                reasons.append("NICE_VS_MUST_CRITICAL")
        elif fuzzy:
            observed={a["modality_candidate"] for a in fuzzy}
            if kind in ("MUST","NICE") and kind not in observed:
                reasons.append("OVERLAPPING_LABEL_DIFFERS")
        else:
            if kind in ("MUST","NICE"):
                reasons.append("REQUIREMENT_NOT_IN_BASELINE")
        if re.search(r"(?i)\b(?:optional|nice.to.have|preferred|mile widziane|atute?m|a plus)\b",quote) and kind=="MUST":
            reasons.append("OPTIONAL_KEYWORDS_CLASSIFIED_MUST")
        if re.search(r"(?i)\b(?:not required|no experience required|nie wymagamy|not necessary)\b",quote) and kind=="MUST":
            reasons.append("NEGATION_CLASSIFIED_MUST")
        if len(quote)==1 and kind=="MUST":
            reasons.append("SINGLE_LETTER_OR_AMBIGUOUS_TOKEN")
        if not reasons:
            continue
        high={"SOURCE_QUOTE_NOT_EXACT","MUST_VS_NICE_CRITICAL","NICE_VS_MUST_CRITICAL",
              "OPTIONAL_KEYWORDS_CLASSIFIED_MUST","NEGATION_CLASSIFIED_MUST",
              "SINGLE_LETTER_OR_AMBIGUOUS_TOKEN"}
        priority="P0" if high.intersection(reasons) else "P1" if "DIRECT_LABEL_CONFLICT" in reasons else "P2"
        issue={
            "posting_id":postid,
            "source":packets[postid]["source"],
            "title":packets[postid]["title"],
            "url":packets[postid]["url"],
            "quote":quote,
            "model_label":kind,
            "extractor_labels":sorted({x["modality_candidate"] for x in (match or fuzzy)}),
            "reasons":reasons,
            "priority":priority,
            "review_status":"REVIEW_REQUIRED",
            "model_source":"claude-haiku-draft",
        }
        issues.append(issue)
        by_posting[postid][priority]+=1
    # Flag particularly risky structured portal metadata even if the model
    # correctly refuses to repeat it (e.g. a bare C in Product Owner musts).
    for postid, previous in base.items():
        packet=packets.get(postid)
        if not packet or packet["split"]!="development":
            continue
        for row in previous:
            quote=row["quote"].strip()
            if row["modality_candidate"]=="MUST" and len(quote)==1:
                issues.append({
                    "posting_id":postid,"source":packet["source"],"title":packet["title"],
                    "url":packet["url"],"quote":quote,
                    "model_label":"OMITTED_OR_NOT_OBSERVED",
                    "extractor_labels":["MUST"],
                    "reasons":["SINGLE_LETTER_OR_AMBIGUOUS_TOKEN","PORTAL_METADATA_REVIEW"],
                    "priority":"P0","review_status":"REVIEW_REQUIRED",
                    "model_source":"portal_structured_candidate",
                })
                by_posting[postid]["P0"]+=1
    order={"P0":0,"P1":1,"P2":2}
    issues.sort(key=lambda x:(order[x["priority"]],x["posting_id"],x["quote"]))
    with (WORK/"review-queue.jsonl").open("w",encoding="utf-8") as f:
        for i in issues:f.write(json.dumps(i,ensure_ascii=False)+"\n")
    summary={
        "status":"MODEL_CANDIDATE_TRIAGE_NO_GOLD",
        "model_claims":len(drafts),
        "model_grounded_claims":sum(x["source_exact"] for x in drafts),
        "model_unanchored_claims":sum(not x["source_exact"] for x in drafts),
        "model_reviewed_postings":len(set(x["posting_id"] for x in drafts)),
        "holdout_sealed_postings":39,
        "issues":len(issues),
        "issues_by_priority":dict(Counter(x["priority"] for x in issues)),
        "postings_with_issues":len(by_posting),
        "example_issues":[{k:x[k] for k in ("posting_id","title","priority","quote","model_label","extractor_labels","reasons")} for x in issues[:10]],
        "human_gold_postings":0,
        "precision":None,
        "recall":None,
    }
    (WORK/"triage-status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
