# Source candidates — 2026-10-07

Purpose: expand the job-market knowledge graph without degrading provenance quality.

## P1 — direct-source candidates

### SOLID.Jobs

Status: **READY_FOR_SOURCE_ARCHAEOLOGY / highest priority**.

Evidence:
- public robots permits crawling except management/admin surfaces;
- public sitemap index includes `sitemap-offers.xml`;
- `sitemap-offers.xml` exposed 3,787 offer URLs during inspection;
- detail URLs contain stable numeric source IDs (`/offer/{id}/...`);
- detail page exposes schema.org `JobPosting` JSON-LD;
- salary, employment form and rich requirement text are present;
- market-facing IT pages report roughly 1.6–1.7k active IT offers and require salary ranges.

Next: SA-SOLID-01 fixture corpus + parser contract + current-offer vs historical-sitemap semantics.

### TeamQuest

Status: **READY_FOR_SOURCE_ARCHAEOLOGY / high priority**.

Evidence:
- robots allows public crawling;
- dedicated `sitemap/praca.xml`;
- current IT page reports 158 offers;
- sitemap inspection returned 248 loc entries, roughly half image URLs and roughly 124 job detail URLs;
- stable numeric identity appears in detail URLs;
- detail HTML contains title, compensation, contract and technology sections.

Risk: the same requisition is often published per city / remote location. Keep source posting identity separate from opportunity resolution.

### IT-Leaders

Status: **DISCOVERY CANDIDATE**.

Evidence:
- public SSR listing and stable-looking numeric offer IDs;
- rich skills, experience, remote and compensation fields;
- no public sitemap found in initial inspection.

Risk: inventory completeness must be proven before crawl-all.

### Michael Page Poland — IT

Status: **DIRECT RECRUITER CANDIDATE**.

Public IT search/sitemap; current public search showed about 88 Poland IT roles.

Risk: advertiser/recruiter/employer/end-client roles must remain separate.

## P2 — high-signal specialist / international

### Hacker News — Who is hiring?

High-signal monthly source for AI, infrastructure, systems, remote and startup role shifts. Identity is monthly-thread/comment based rather than classic board posting identity.

### Wellfound

Research-only until an approved transport exists. Public search exposes Poland startup/tech roles, but direct automated HTTP returns a security check. Do not bypass it.

### EuroTechJobs

Low-volume direct candidate; useful category metadata, lower priority than SOLID/TeamQuest.

## P3 — aggregators / secondary evidence

- Indeed — large Poland coverage, high duplicate risk.
- LinkedIn Jobs — very large market coverage; research counts only until an approved acquisition route exists.
- Jobsora — very large aggregator; useful for discovery, not preferred canonical evidence.
- Jooble — explicitly an aggregator; secondary provenance unless directly-published Jooble posting is identified.
- Remotive / global remote aggregators — useful later as a separate REMOTE_GLOBAL segment.

## P4 — access-limited / do not bypass

- Wellfound direct automated access: security check.
- LinkedIn: no approved crawler transport established.
- Welcome to the Jungle: personalized search requires account; no acquisition contract established.
- Direct Pracuj: managed challenge; existing Pracuj data remains SECONDARY_PUBLIC_INDEX.

## Recommended sequence

1. SOLID.Jobs
2. TeamQuest
3. IT-Leaders
4. Michael Page / selected recruiter boards
5. HN Who is hiring? as separate international/high-signal segment
6. only then aggregators, with explicit secondary provenance and duplicate-risk controls

Do not mix direct-source market counts with aggregator counts without provenance-aware weighting.
