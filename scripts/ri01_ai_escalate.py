#!/usr/bin/env python3
"""Send only irreducible domain disputes to Ryba; route routine faults to QA."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/".local-evidence/ri01/ai-review"
SONNET=WORK/"sonnet-crosscheck"


def main():
    all_issues=[json.loads(x) for x in (WORK/"review-queue.jsonl").open(encoding="utf-8")]
    packets={x["posting_id"]:x for x in map(json.loads,(ROOT/".local-evidence/ri01/review-packets.jsonl").open(encoding="utf-8"))}
    cross=json.loads((SONNET/"cross-model-disagreements.json").read_text(encoding="utf-8"))
    business=[]
    seen=set()
    for mismatch in cross:
        postid=mismatch["posting_id"]
        packet=packets[postid]
        item={"posting_id":postid,"source":packet["source"],"title":packet["title"],
              "url":packet["url"],"quote":mismatch["quote"],
              "model_label":mismatch["second_label"],
              "extractor_labels":mismatch["first_labels"],
              "priority":"P0","reasons":["TWO_INDEPENDENT_MODEL_LABELS_DISAGREE"],
              "review_status":"BUSINESS_ADJUDICATION_OPEN",
              "model_source":"haiku_vs_sonnet"}
        k=postid,item["quote"]
        if k not in seen:business.append(item);seen.add(k)
    def ranking(issue):
        reasons=set(issue["reasons"])
        if reasons & {"MUST_VS_NICE_CRITICAL","NICE_VS_MUST_CRITICAL","NEGATION_CLASSIFIED_MUST"}:
            return (0, issue["posting_id"])
        if "OPTIONAL_KEYWORDS_CLASSIFIED_MUST" in reasons:
            return (1, issue["posting_id"])
        return (2, issue["posting_id"])
    for issue in sorted(all_issues, key=ranking):
        reasons=set(issue["reasons"])
        major=bool(reasons & {"MUST_VS_NICE_CRITICAL","NICE_VS_MUST_CRITICAL",
                              "NEGATION_CLASSIFIED_MUST",
                              "SINGLE_LETTER_OR_AMBIGUOUS_TOKEN"})
        if not major:
            continue
        k=(issue["posting_id"],issue["quote"])
        if k in seen:
            continue
        if len(business)>=19:
            continue
        item={**issue, "priority":"P0", "review_status":"BUSINESS_ADJUDICATION_OPEN"}
        business.append(item)
        seen.add(k)
    # Deliberately add one important semantic omission that belongs to the
    # domain decision boundary (required real production experience).
    sample="nofluffjobs:NZLSCSBX"
    if sample in packets:
        quote="Production experience with OVS / OVN"
        k=(sample,quote)
        if k not in seen:
            packet=packets[sample]
            business.append({
                "posting_id":sample,"source":packet["source"],"title":packet["title"],
                "url":packet["url"],"quote":quote,"model_label":"MUST?",
                "extractor_labels":["UNKNOWN"],"priority":"P0",
                "reasons":["DOMAIN_SEMANTIC_REVIEW_REQUIRED"],
                "review_status":"BUSINESS_ADJUDICATION_OPEN",
                "model_source":"focused_domain_discovery",
            })
            seen.add(k)
    with (WORK/"escalation-queue.jsonl").open("w",encoding="utf-8") as f:
        for x in business:f.write(json.dumps(x,ensure_ascii=False)+"\n")
    remaining=[x for x in all_issues if (x["posting_id"],x["quote"]) not in seen]
    # Baseline UNKNOWN -> model MUST is expected new model evidence, not by
    # itself a conflict requiring 600+ manual reviews. Flag actual risks only.
    actionable={"SOURCE_QUOTE_NOT_EXACT","SOURCE_JSON_PATH_UNRESOLVED",
                "OPTIONAL_KEYWORDS_CLASSIFIED_MUST","NEGATION_CLASSIFIED_MUST",
                "MUST_VS_NICE_CRITICAL","NICE_VS_MUST_CRITICAL",
                "SINGLE_LETTER_OR_AMBIGUOUS_TOKEN"}
    qa=[x for x in remaining if set(x["reasons"]) & actionable]
    info=[x for x in remaining if not (set(x["reasons"]) & actionable)]
    # Second, stricter archive field resolution can find problems even when
    # model quote matches a combined source text projection.
    fullfield=WORK/"ai-evidence-verified.jsonl"
    if fullfield.exists():
        existing={(x["posting_id"],x["quote"]) for x in qa}
        for row in map(json.loads, fullfield.open(encoding="utf-8")):
            if row["source_exact"] and not row["source_field_exact"]:
                key=(row["posting_id"],row["quote"])
                if key in existing:continue
                packet=packets[row["posting_id"]]
                qa.append({"posting_id":row["posting_id"],"source":packet["source"],
                          "title":packet["title"],"url":packet["url"],"quote":row["quote"],
                          "model_label":row["kind_draft"],"extractor_labels":[],
                          "priority":"P1","reasons":["SOURCE_JSON_PATH_UNRESOLVED"],
                          "review_status":"TECHNICAL_EVIDENCE_REVIEW",
                          "model_source":"mechanical_field_grounding"})
                existing.add(key)
    with (WORK/"qa-queue.jsonl").open("w",encoding="utf-8") as f:
        for x in qa:f.write(json.dumps(x,ensure_ascii=False)+"\n")
    summary={"status":"ESCALATION_PROPOSALS_NOT_GOLD",
        "total_ai_extractor_observations":len(all_issues),
        "cross_model_disagreements":len(cross),
        "business_escalations":len(business),
        "qa_routed_issues":len(qa),
        "informational_unverified_label_promotions":len(info),
        "human_gold_postings":0,
        "business_decisions_applied":0,
        "precision":None,"recall":None}
    (WORK/"escalation-status.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
