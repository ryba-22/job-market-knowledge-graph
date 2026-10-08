# APLIKUJ-IT-V2 — lossless category discovery and reviewable classification

## Problem / boundary

The old `technical-it-v1` pipeline discarded records twice based solely on job title: at `AplikujSource.discover()` and again after `parse_detail()` in the file-backed acquisition path (including deleting raw observations). Such records could be genuine IT jobs with ambiguous titles. The earlier archival cleanup removed 13,717 records from an unscoped historic crawl; that previous deletion is not magically reversed.

## Decided model

- `CategoryListing` identifies **candidate source posting IDs**; category membership is *not* proof of IT eligibility.
- `Posting / RawObservation` are immutable source evidence. **No title-based rejection or deletion** during discovery or acquisition, even for promoted, ambiguous, industrial and clearly non-IT jobs.
- `ITAssessment` is a separate, versioned *decision* stored in `assessments.jsonl.gz`, linked by `(source, source_posting_id, raw_payload_sha256)` to the raw observation. It does not change the semantic source revision hash.
- Assessment states: `IT_CONFIRMED`, `NON_IT_CONFIRMED`, `REVIEW_REQUIRED`. The first two require multiple independent signals (title + actual job duties, or title + industry + nontechnical duties); missing, contradictory or invalid evidence goes to review. All three statuses are archived and count toward acquired postings. These statuses are **heuristic classifications, not human-verified truth**.
- A classifier exception produces an assessment `REVIEW_REQUIRED` with `ASSESSMENT_ERROR`, not a dropped posting.
- Source/posting identity, classification policy revision and origin/payload evidence are preserved independently for future reclassification.

## Invariants and executable boundaries

1. `discovered category IDs = queue IDs` for a full successful discovery. Previous audit fixture enumerated 509 distinct Aplikuj IDs across 11 pages. Regression fixtures confirm the new source discovery returns all 509 regardless of the old title heuristic.
2. `planned = postings + source_gone` (on a completed error-free v2 chunk); `excluded_non_it = 0`. For successful parsed postings, count `IT_CONFIRMED + NON_IT_CONFIRMED + REVIEW_REQUIRED = postings`.
3. Source identities in `corpus.jsonl.gz` and assessment sidecar are exactly equal; both correspond to raw observations of the same source revision. A separate v2 verifier checks IDs, hashes, counts, raw linkage and failures.
4. A v2 chunk is only considered completed when scope is exactly `it-category-v2` with consistent assessment accounting. Old v1 manifests or pruned chunks cannot be accepted as v2.
5. Existing v1 archive files cannot be overwritten by a v2 worker; the default v2 output path is separately namespaced (`.local-crawl/scale-04-it-v2`, `.local-evidence/scale-04-it-v2`).
6. The historical title-based `clean_aplikuj_cache --apply` is permanently disabled. Its read-only audit remains available; it does not mutate files.
7. Inventories may only reuse Aplikuj data from complete v2 manifests. Old v1 survivors, even if marked known in a base corpus, are never excluded from new acquisition solely for that reason.
8. Discovery fails explicitly when an expected category page has no job cards or the bounded pagination limit is reached while more pages exist; no false "100%" from an empty rendered page.

## Verification / next actions

- Unit tests cover title ambiguity, conflicting evidence, category listing preservation including all historic 509 IDs, all three classifications, manifest scope rejection, legacy cleanup disabled, lossless synthetic acquisition, and raw/assessment integrity failures.
- `python -m ingestion.verify_aplikuj_v2 --root .local-crawl/scale-04-it-v2` checks batches **after** they are acquired. When no v2 batches exist, status is `NOT_RUN`, not `PASS`.
- **No crawler was resumed** in this task. The previous historical pruned records were not re-downloaded. The v2 real-data verification gate remains `NOT_RUN` until explicitly authorized acquisition.
- Before an authorized resumption, produce a **new** Aplikuj category inventory and chunk plan with `aplikuj_scope=it-category-v2`; do not edit or reuse the old full-site 40,634-ID plan. Compare the newly enumerated live category ID count to the portal's own counter as additional completeness evidence.
- Run manual adversarial review on random positive, negative and `REVIEW_REQUIRED` samples; tune the independently versioned assessment policy rather than suppressing difficult records.

## Open questions

- Which IT-adjacent professions (UX, product, embedded industrial automation, IT sales, ERP consulting) belong to the final market definition? No automatic destructive policy until domain scope is agreed.
- Geography and cross-portal opportunity resolution remain separate questions; a listing count does not equal deduplicated Polish IT vacancies.
