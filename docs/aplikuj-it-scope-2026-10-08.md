# APLIKUJ-IT-01 — historical source restriction, stop and cleanup

> **Superseded by `docs/aplikuj-it-category-v2-2026-10-08.md`.** This is a historical record of the v1 title-based cleanup, not the active ingestion policy. Its automatic title-based deletion has been disabled. The previously excluded 13,717 records cannot be recovered without authorized reacquisition.

Date: 2026-10-08. User instruction: stop downloading, restrict Aplikuj.pl to IT, remove non-IT.

## Facts / checkpoint

- User-requested stop: local workers for SCALE-04/Aplikuj and SCALE-02/RocketJobs etc. terminated; no crawler restarted.
- Source defect: previous Aplikuj discovery traversed the unfiltered `/sitemap/offer_index.xml`, capturing all industries. Old frozen inventory contains 40,634 Aplikuj URLs, **not** a verified IT count.
- Aplikuj public IT category: `https://www.aplikuj.pl/praca/it-informatyka`. Its listing itself includes unrelated and promoted items; category membership alone is insufficient.
- Completed local batches before cleanup: 55 × up to 250 = 13,750 parsed Aplikuj offers.
- Cleanup executed: **13,717 non-technical-IT postings removed**, **33 retained**, across 55 locally completed chunks, 0 cleanup failures.
- Removal includes both compact `corpus.jsonl.gz` and corresponding full HTML raw observations; manifests and checksums rewritten to reflect retained records and excluded counts.
- Old discovery inventory and old chunk plan remain as historic **ID-only provenance**, not input for any subsequent crawl. They are explicitly rejected by executable scope gates.
- `.local-crawl/scale-04/status.json` is marked `PAUSED_BY_USER`, `UNSCOPED_INVENTORY_REJECTED`; other active source statuses marked paused.
- Unit/regression suite: 89 passing tests at the checkpoint.

## Contract

- Aplikuj discovery must start from the public **IT category listing**, never the all-jobs sitemap.
- A title-based conservative technical-IT filter removes off-topic promoted cards from discovery, including CNC, industrial robots, IT sales, education, and non-IT admin roles.
- After fetching, the same gate checks the parsed position title. Non-IT content is excluded from BOTH semantic corpus and local raw payload archive.
- For Aplikuj, the inventory manifest has `aplikuj_scope=technical-it-v1`; chunk planning propagates the token and crawler validates it before any network acquisition.
- Runtime accounting is `planned = postings + source_gone + excluded_non_it` on completed chunks. Raw archive rows = `planned - excluded_non_it`.
- Technical-IT scope is **not** equivalent to all technology-company jobs. Generic/borderline titles are held out rather than asserted as IT.

## Future resume — NOT EXECUTED

1. Explicitly authorize resume first; do not restart the old 40k inventory/plan.
2. Rebuild new inventory using `python -m ingestion.build_scale04_inventory --base-corpus data/corpora/corpus-10/corpus.jsonl.gz --out data/inventories/scale-04-it-only` (also discovers the other configured SCALE-04 sources, which must not be fetched unless separately requested).
3. Create a new plan with `python -m ingestion.plan_inventory_chunks --inventory data/inventories/scale-04-it-only/inventory.jsonl.gz --out data/inventories/scale-04-it-only/chunks.json`.
4. Only then run `python -m ingestion.run_file_backed_plan --plan data/inventories/scale-04-it-only/chunks.json --sources aplikuj --out-root .local-crawl/scale-04-it-only --raw-root .local-evidence/scale-04-it-only --status .local-crawl/scale-04-it-only/status.json`.
5. Reconcile source IDs and IT classification before merging any new slices into an analytical corpus.

## Limitations

- The IT category listing is a live, time-varying discovery surface. No new bulk crawl or coverage count was executed after the user stopped downloading.
- The title gate intentionally has false-negative risk, especially for generic or blended technology roles; manual adjudication should precede changing classification rules.
- The 33 retained records are from the *previously downloaded* unscoped sample; they do not represent all current IT offers at Aplikuj.pl.
