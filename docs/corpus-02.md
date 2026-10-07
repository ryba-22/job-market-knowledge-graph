# CORPUS-02 — expand the market corpus

Goal: increase the durable offer corpus without modifying the frozen ER-EVAL-02 benchmark.

## Phase 1

Collect 100 current postings from each already-understood source:

- The Protocol: 100
- Just Join IT: 100

Target: at least 190 successful postings total, allowing a small number of lifecycle 404s.

## Boundary

This corpus is observational data, not a labeled entity-resolution benchmark.

It stores:
- stable source identity,
- source URL,
- title,
- source projection,
- normalized semantic projection,
- revision hash,
- organization mention,
- parser/normalizer/transport versions,
- immutable RawObservation SHA-256 + byte count + archive key.

The compact corpus does not embed rendered HTML. Full RawObservation remains an ingestion/archive concern.

## Next

After CORPUS-02 is frozen:
1. derive a larger candidate/reference set from the 200 postings;
2. measure candidate-generation coverage;
3. add new sources only through Source Archaeology before ingestion.
