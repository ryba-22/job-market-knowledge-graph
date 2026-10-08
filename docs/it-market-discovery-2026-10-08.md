# DISCOVERY-IT-02 — real job-offer inventory, 2026-10-08

## Decision boundary

Read-only, **listing-only** discovery. User's earlier stop request is still binding for full offer-detail acquisition. No resumed queue, no new raw offer payload crawl, no production deployment.

**Core distinction:** `portal counter ≠ discovered unique source IDs ≠ verified technical IT postings ≠ deduplicated recruitment opportunities`.

## Verified now

| Source | Source UI / public counter | Identity evidence | Classification / scope caveat |
| --- | ---: | --- | --- |
| Aplikuj.pl `/praca/it-informatyka` | 509 | **509 distinct posting IDs** enumerated from exactly 11 listing pages; 50×10 + 9 | Broad portal IT category includes industrial/non-IT and ambiguous titles. Current conservative *title-only* filter flags 114, leaves 395 unaccepted; neither group is audited as ground truth. |
| Just Join IT `all-locations` | **19,756** on official page | Current official SSR listing emits 50 distinct URLs per page. Page 31 is accessible and different from page 1. Prior fixed 30-page ingestion discovered 1,405 IDs. | ALL locations, including outside Poland. 19,756 is not a Poland-only count; also not a deduplicated cross-board opportunity count. |
| No Fluff Jobs `/pl/it` | 901 (public search result checked 2026-10-08; web index roughly two days older) | Older source inventory on 2026-10-07 held 2,616 records with `region=pl` API and no category criteria. | The 901 belongs to free-text search `it`, **not all IT**. The 2,616 source inventory mixed job categories. Current direct API access may respond 403; no bypass. |
| TeamQuest `/praca-w-it` | **109** on listing at this discovery run | Prior source sitemap inventory had 124 URLs at another time. | Agency IT-facing search may include recruiters and repeated locations. Distinct requisitions not reconciled. |
| Bulldogjob | no verified current exact count | Previous direct sitemap inventory had 870 source postings | IT-oriented but international, some non-technical roles; previous count is NOT necessarily currently active. |
| RocketJobs | no IT-only counter established | Previous source inventory had 15,468 IDs | Broad non-IT portal, must not treat as IT population. |
| SOLID.Jobs | no IT-only counter established | Previous frozen corpus includes 3,235 source IDs | Broad job portal, mixed professions. |
| Pracuj.pl / TheProtocol | not verified current active inventory | Previous Pracuj subset secondary-indexed; TheProtocol official total published-count historical | Do not equate all-time published listings to currently active posts; no challenge bypass. |

## Evidence and failure findings

1. **JustJoinItAdapter has `for page in range(2,31)` hard ceiling.** `page=31` returns a fresh 50-posting page with zero overlap with the sampled page 1; `?from=100` is ignored as a pagination control (page 1 content repeated). Therefore previous `100%` means successful processing of a **capped discovery set**, not complete market coverage. No full 19,756-offer download attempted.
2. **Aplikuj is fully indexed at category level (509/509 unique IDs).** The 114 title-matched records are **not a verified lower bound** on technical positions (false positives possible), and the other 395 are **not validated non-IT** (false negatives definitely present, e.g., infrastructure and security job titles). Keep all candidate IDs in a listing-only audit instead of deleting uncertain cases.
3. **Cross-site duplicate risk confirmed.** Frozen `CORPUS-10` (6,320 rows) yields 99 distinct normalized `(employer, title)` pairs that occur on ≥2 job boards, covering 420 rows. These are *duplicate candidates*, not dedup-proven shared requisitions: identical title/employer may mean multiple locations or vacancies.
4. Geography is inconsistent (Just Join IT global, other sources Poland-filtered or partial). Country, remote eligibility, contract and employer identity need separate fields before counting Polish opportunities.

## Artifacts

- `reports/discovery-2026-10-08/discovery.json`: official counter and page-by-page diagnostics with observed times; source IDs + samples.
- `reports/discovery-2026-10-08/aplikuj-listing-ids.jsonl`: 509 discovered source IDs and listing titles only. **No full job descriptions.**
- `reports/discovery-2026-10-08/justjoin-pagination.json`: five-page limited pagination comparison.
- Reproducible bounded discovery code: `scripts/discovery_iteration_20261008.py` and `scripts/check_justjoin_pagination.py`.

## Acceptance gate for a truthful Polish IT total

1. Lock population contract: active technical/digital IT roles with workplaces in Poland **or explicitly accepting applicants living in Poland**, one posting identity per source; global market tracked separately.
2. Discover all pages/records by platform-supported pagination. Capture total/page count, unique ID count, 404/gone count, page checksum/overlap, and explicit exhaustion. Never call a capped index `100% market coverage`.
3. Obtain category and role semantics without discarding undecidable titles. Classify `IT_CONFIRMED`, `NON_IT_CONFIRMED`, `REVIEW_REQUIRED` from evidence with manual false-negative QA. `REVIEW_REQUIRED` is not the same as `NON_IT`.
4. Resolve same cross-posted opportunity across boards using employer, normalized title, location, recruiter vs hiring company, and temporal validity. Do not merge multi-position or multi-location postings automatically.
5. Report both source-local posting IDs and validated unique opportunity count with explicit uncertainty. The latter is currently **NOT ESTABLISHED**.

## Pause / side effects

Previous Aplikuj detail crawler and other workers remain paused (`PAUSED_BY_USER`). Only listing pages and metadata pages were read in this iteration. No restart or deletion. No production side effects.
