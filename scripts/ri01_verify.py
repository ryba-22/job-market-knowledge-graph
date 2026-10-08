#!/usr/bin/env python3
"""Independent mechanical grounding verification over RI-01 candidate output.

Grounding checks only that the quote is traceable to a saved field/DOM projection;
it DOES NOT certify semantics, must/nice correctness, completeness, or recall.
"""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from ingestion.requirement_intelligence import anchored_in_source, identity

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local-evidence/ri01"
with (OUT / "assertion-candidates.jsonl").open(encoding="utf-8") as f:
    assertions = [json.loads(line) for line in f]
identities = {a["posting_id"] for a in assertions}
records = {}
with gzip.open(ROOT / "data/corpora/corpus-10/corpus.jsonl.gz", "rt", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)
        if identity(record) in identities:
            records[identity(record)] = record
by_source = defaultdict(Counter)
failure_examples = []
for claim in assertions:
    source = claim["source"]
    valid = claim["posting_id"] in records and anchored_in_source(records[claim["posting_id"]], claim)
    by_source[source]["checked"] += 1
    by_source[source]["grounded" if valid else "ungrounded"] += 1
    if not valid and len(failure_examples) < 20:
        failure_examples.append({
            "posting_id": claim["posting_id"],
            "source_path": claim["source_path"],
            "quote_preview": claim["quote"][:90],
        })
total = sum(c["checked"] for c in by_source.values())
grounded = sum(c["grounded"] for c in by_source.values())
report = {
    "type": "mechanical_grounding_not_semantic_quality",
    "checked": total, "grounded": grounded, "not_grounded": total-grounded,
    "grounding_rate": grounded / total if total else None,
    "by_source": {source: dict(counts) for source, counts in sorted(by_source.items())},
    "failures": failure_examples,
}
(OUT / "grounding-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
