# RUNBOOK

## WHEN

Use this repository when the task concerns job-offer evidence, market-wide signals about roles/capabilities/processes/technologies, ingestion of job postings, or rebuilding the job-market graph.

Do not use it as authority for a personal career decision, a universal engineering best practice, or a project-specific architecture decision.

## INPUT

- one or more job offers or configured source connectors;
- source URL/provider and capture timestamp;
- the current schemas under `schema/`;
- the current ingestion and verification contracts.

## FLOW

1. Capture the source as evidence without treating employer wording as universal truth.
2. Normalize the offer into the repository schema.
3. Run source-specific and production-boundary verification.
4. Enrich only fields supported by evidence or explicit inference labels.
5. Build/update graph nodes and edges deterministically.
6. Rebuild market snapshots/reports.
7. Run tests/evals and record provenance for material claims.

## OUTPUT

- normalized job evidence;
- graph nodes/edges;
- market snapshot or targeted analysis;
- verification/eval evidence for the changed ingestion or extraction behavior.

## EVIDENCE

A result is supported only when source provenance is retained and the relevant validation/tests pass. Distinguish `FACT` from interpretation and personal decision.

## STOP

Stop when additional offers or enrichment are unlikely to change the current decision/market conclusion, or when the requested source quota is satisfied. Do not crawl merely to increase corpus size.

## HANDOFF

Reusable market findings may be referenced by portfolio/career analysis. Promotion into PMA, PEOS, Atlas or another knowledge corpus is deliberate and requires that repository's own evidence/governance process; it is never automatic.
