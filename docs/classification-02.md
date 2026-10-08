# CLASSIFICATION-02 — Aplikuj.pl (2026-10-08)

**Implementation / archival consistency: PASS. Independent classification validity: NOT YET ESTABLISHED.**

## Scope

The input is the frozen, verified 509 source posting IDs from the Aplikuj IT category (it-category-v2). Each record provides a structured JobPosting.description. This is not equivalent to 509 current, unique, technical IT jobs. No network requests or recrawls are made in this stage.

Source facts, raw HTTP observations, original normalized projections and the first classifier sidecars remain unchanged. New results are stored in a separate derived archive linked by source_posting_id, revision_id and raw_payload_sha256. Decisions contain version, evidence codes and normalized source-text excerpts; they are not source facts or literal original HTML citations.

## Classification contract

- IT_CONFIRMED: rule-based technical/digital job assessment supported by title plus job duties/technology or two corroborating duty signals.
- NON_IT_CONFIRMED: rule-based clear occupation outside technical IT (teaching, sales, transport, industrial CNC/robots, office administration, etc.). This does not delete the source record.
- REVIEW_REQUIRED: incomplete or conflicting evidence and hybrid/borderline scope (ERP presales, industrial automation/PLC, telecom hardware installation, security policy/document administration, mixed commercial/frontend roles).
- Technical IT occupation is not identical to IT-industry employer, IT-category search result or simply mention of technology.

## Results and diagnostics

| Assessment | Previous v1 | CLASSIFICATION-02 |
|---|---:|---:|
| IT_CONFIRMED | 38 | 93 |
| NON_IT_CONFIRMED | 6 | 149 |
| REVIEW_REQUIRED | 465 | 267 |
| **Total** | **509** | **509** |

206 of 509 individual records changed their category. The preserved-source and new assessment archive consistency checks both returned PASS.

An author-curated diagnostic set of 64 real source IDs, reviewed with descriptions, yielded 63 matching decisions. The remaining difference: the generic 'Programista k/m' with mechanical DXF/STEP references was safely left REVIEW_REQUIRED rather than automatically excluded. This diagnostic set was used during rule development and is NOT an independently blinded test; 63/64 cannot be presented as accuracy, precision or recall. Do not treat 93 as manually verified genuine IT vacancies.

## Artifacts

- Source (untouched): .local-crawl/scale-04-it-v2/aplikuj/*/{corpus.jsonl.gz,assessments.jsonl.gz} and .local-evidence/scale-04-it-v2/aplikuj/*/raw-observations.jsonl.gz
- New sidecar: .local-crawl/classification-02/assessments.jsonl.gz
- Manual review queue (267): .local-crawl/classification-02/review-queue.jsonl.gz
- Fingerprint and counts: .local-crawl/classification-02/manifest.json
- Aggregates: reports/classification-02/{summary.json,diagnostic-eval.json}
- Curated cases: tests/fixtures/classification02_curated_labels.json

## Offline reproducibility

```bash
cd ~/job-market-knowledge-graph-scale05
.venv/bin/python -m ingestion.run_classification02
.venv/bin/python -m ingestion.run_classification02 --verify-only
.venv/bin/python -m ingestion.eval_classification02
jq '.status_counts, .review_queue_count' reports/classification-02/summary.json
gzip -dc .local-crawl/classification-02/review-queue.jsonl.gz | jq -s '.[0:5] | map({source_posting_id,title,reason_code})'
```

## Next gates / limitations

1. Obtain independent, blinded, stratified human labels for ~200 postings, including source spans and boundary roles, with adjudication.
2. Measure precision, recall, unsafe positive IT assignments, missed IT roles, review/abstention rate and correctness of evidence spans against held-out annotations.
3. Review the remaining 267 candidates; improve policies only from adjudicated failure patterns, version the rules and preserve old sidecars.
4. Site-active validity, Poland geography and duplicate vacancy resolution require separate evidence; this stage does not estimate the complete Polish IT labor market.

Previous crawler stop is preserved; no production deployment or external side effects.
