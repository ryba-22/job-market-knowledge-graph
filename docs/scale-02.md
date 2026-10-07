# SCALE-02 — full direct-source inventory and resumable crawl-all queue

Base corpus: CORPUS-06 with 1,583 historical/active source-local postings.

## Frozen inventory

Captured on 2026-10-07 from direct public discovery surfaces.

| Source | Discoverable now | Present in current discovery and already in CORPUS-06 | Unknown in inventory |
| --- | ---: | ---: | ---: |
| Just Join IT | 1,405 | 381 | 1,024 |
| No Fluff Jobs | 2,616 | 399 | 2,217 |
| RocketJobs | 15,468 | 400 | 15,068 |
| Bulldogjob | 870 | 213 | 657 |
| **Total** | **20,359** | **1,393** | **18,966** |

The known count is intersection-with-current-discovery, not historical corpus size. Missing historical records are expected when offers expire or disappear.

## Crawl-all model

The 18,966 unknown identities are frozen into 78 deterministic chunks of at most 250 postings:

- Bulldogjob: 3 chunks
- Just Join IT: 5
- No Fluff Jobs: 9
- RocketJobs: 61

A worker consumes an exact frozen chunk and never rediscovers identities during detail acquisition. Each chunk emits:

- compact semantic corpus slice,
- source manifest,
- run report,
- full RawObservation archive,
- raw manifest.

Retries and pacing remain source-specific; Bulldogjob uses the conservative delay.

## Completeness boundary

"Crawl all" means all identities visible in the frozen direct-source inventory.

This currently applies to:
- Just Join IT
- No Fluff Jobs
- RocketJobs
- Bulldogjob

It does not claim full-site completeness for:
- Pracuj: current automated transport is SECONDARY_PUBLIC_INDEX, not direct exhaustive discovery.
- The Protocol: current official MCP transport does not expose a complete unique identity inventory.

## Analysis boundary

After acquisition, all successfully parsed postings can flow through the same semantic projection and knowledge-graph analysis. Source provenance remains available so secondary/direct evidence can be weighted separately.

## Scale discipline

- inventories are immutable point-in-time snapshots;
- chunk processing is resumable and idempotent by source identity;
- prior corpus versions are never replaced;
- lifecycle drift is measured by comparing later inventories, not by mutating history;
- full raw payload archives remain evidence, compact corpus remains analytical input.
