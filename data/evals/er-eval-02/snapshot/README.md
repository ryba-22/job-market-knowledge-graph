# ER-EVAL-02 frozen benchmark

This directory is the deterministic, repository-owned benchmark snapshot for ER-EVAL-02.

## Contents

- 26 source-local JobPostings participating in the benchmark
- 19 adjudicated cross-source pairs
- final labels: 1 SAME_OPPORTUNITY, 4 DISTINCT_OPPORTUNITY, 14 UNRESOLVED
- source and normalized projections used by the evaluation
- candidate and decision evidence
- stable source identities
- normalized revision hashes
- parser / transport versions
- SHA-256 and byte length of the original RawObservation payload for every posting

The compact snapshot is gzip-compressed and split into fixed chunks only to keep Git objects small and reviewable. `manifest.json` pins every chunk checksum plus the checksum of the reconstructed compressed and uncompressed snapshot.

## Raw evidence

The benchmark intentionally does not embed ~14 MB of rendered portal HTML because most of that size is repeated UI/application shell and is not required by the identity benchmark.

The exact full-RawObservation freeze that produced this snapshot was verified in GitHub Actions run `37604848300`, artifact `11474143690`, digest:

`sha256:746869ec10ef27a23dda980246d836d54977230676f69de9839b33ca5ff1e2c3`

That artifact is supplementary provenance. The benchmark itself does **not** depend on the artifact, PostgreSQL, Just Join IT, The Protocol, MCP, or network access.

Each frozen posting retains the SHA-256 and byte count of its original RawObservation so a separately archived raw payload can be checked against the benchmark provenance.

## Offline replay

```bash
python -m ingestion.replay_frozen_benchmark \
  --snapshot data/evals/er-eval-02/snapshot
```

Acceptance:

```text
26 postings
19 pairs
1 SAME_OPPORTUNITY
4 DISTINCT_OPPORTUNITY
14 UNRESOLVED
network_used = false
database_used = false
```

This dataset is an evaluation snapshot, not a production source of job-market truth. Live crawling remains a separate observation workflow.
