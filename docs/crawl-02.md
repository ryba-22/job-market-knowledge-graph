# CRAWL-02 — real discovery + batch ingestion

## Problem

The repository previously started at curated analyses in `data/jobs/`.
That is an analytical layer, not a faithful acquisition model.

CRAWL-02 adds a separate evidence pipeline:

```
public job board
→ discovery
→ raw observation
→ source-local JobPosting
→ append-only revision
→ OrganizationMention
→ conservative OrganizationCandidate
→ cross-source MatchCandidate
→ curated analysis (later)
→ knowledge graph
```

The crawler does **not** write directly into `data/jobs/`.

## Sources

First production slice:
- The Protocol — SSR listing/detail
- Just Join IT — SSR listing/detail

Browser automation and undocumented JJIT APIs are not happy-path dependencies.

## Batch contract

CI runs:
1. discover at least 50 current postings per source,
2. ingest details into PostgreSQL,
3. run the same batch a second time,
4. prove the second pass yields at least 100 `UNCHANGED` lifecycle observations,
5. seed OrganizationCandidate records from exact source mentions as **LOW-confidence hypotheses**,
6. generate cross-source MatchCandidate records only for same normalized title + organization mention,
7. never destructively merge source postings.

## Epistemic contract

`FACT != INFERENCE != HYPOTHESIS != DECISION`

Current ORG seed:
- source company mention: FACT,
- ADVERTISER participation: FACT about source presentation,
- canonical organization candidate from exact normalized name: HYPOTHESIS,
- employer/end-client: unresolved.

Current ER seed:
- same title + same org mention: MatchCandidate,
- identity is explicitly **not asserted**.

## Failure semantics

A detail parse failure is not `SOURCE_REMOVED`.
A failed network request is not a vacancy closure.
An expired posting is not proof that hiring ended.

## Acceptance evidence

The GitHub Actions workflow `CRAWL-02 real batch` is the executable checkpoint.
It uses a disposable PostgreSQL service and uploads:
- `reports/crawl-02-first.json`
- `reports/crawl-02-second.json`
- `reports/crawl-02-verification.json`

The workflow fails if either source yields fewer than 50 stored JobPostings or if the recrawl does not prove idempotency.
