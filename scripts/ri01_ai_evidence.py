#!/usr/bin/env python3
"""Verify AI first-pass quotes against exact source fields in frozen CORPUS-10."""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from ingestion.requirement_intelligence import (
    identity, source_segments, source_projection_text,
)

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/".local-evidence/ri01/ai-review"


def main():
    raw=OUT/"ai-firstpass.jsonl"
    if not raw.exists():
        raise SystemExit("AI firstpass output missing")
    claims=[json.loads(l) for l in raw.open(encoding="utf-8")]
    wanted={x["posting_id"] for x in claims}
    with gzip.open(ROOT/"data/corpora/corpus-10/corpus.jsonl.gz","rt",encoding="utf-8") as f:
        records={}
        for line in f:
            record=json.loads(line)
            key=identity(record)
            if key in wanted:records[key]=record
    if set(records)!=wanted:
        raise SystemExit("Missing source posting IDs in frozen corpus")
    fields={}
    for rid, record in records.items():
        source_paths={seg[0] for seg in source_segments(record)}
        field_content=[]
        for path in sorted(source_paths):
            text=source_projection_text(record,path)
            if isinstance(text,str):
                field_content.append((path,text))
        fields[rid]=field_content
    results=[]
    for item in claims:
        record=records[item["posting_id"]]
        quote=item["quote"]
        options=[(path,content.find(quote)) for path,content in fields[item["posting_id"]] if quote in content]
        grounded=bool(options) and item["source_exact"]
        selected=options[0] if options else (None,None)
        result={**item,"source_path":selected[0],
            "source_path_start":selected[1],"source_path_end":selected[1]+len(quote) if grounded else None,
            "source_field_exact":grounded,"source_revision_id":record.get("revision_id"),
            "source_raw_payload_sha256":record.get("raw_payload_sha256"),
            "evidence_status":"EXACT_SOURCE_FIELD" if grounded else "SOURCE_EVIDENCE_REVIEW_REQUIRED"}
        results.append(result)
    with (OUT/"ai-evidence-verified.jsonl").open("w",encoding="utf-8") as f:
        for x in results:f.write(json.dumps(x,ensure_ascii=False)+"\n")
    summary={"status":"MECHANICAL_FIELD_GROUNDING_ONLY",
        "total_claims":len(results),
        "exact_in_archived_field":sum(x["source_field_exact"] for x in results),
        "unresolved":sum(not x["source_field_exact"] for x in results),
        "exact_postings":len({x["posting_id"] for x in results if x["source_field_exact"]}),
        "review_required_by_source":dict(Counter(
            r["posting_id"].split(":",1)[0] for r in results if not r["source_field_exact"])),
        "semantic_correctness_evaluated":False,"gold_quality_precision":None,"gold_quality_recall":None}
    (OUT/"ai-field-grounding.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
