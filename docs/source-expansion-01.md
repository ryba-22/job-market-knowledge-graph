# SOURCE-EXPANSION-01 — six-source representative market corpus

## Goal

Expand CORPUS-02 from 200 offers across two sources to a multi-source corpus suitable for broader market analysis.

Target expansion:

- No Fluff Jobs: 75
- RocketJobs: 75
- Bulldogjob: 75
- Pracuj.pl: 75 secondary observations

Combined with CORPUS-02:

- Just Join IT: 150
- The Protocol: 50
- No Fluff Jobs: 75
- RocketJobs: 75
- Bulldogjob: 75
- Pracuj.pl: 75

Target total: 500 source-local JobPostings across six market sources.

## Source archaeology

### No Fluff Jobs — DIRECT

Transport:
- public search REST endpoint: `/api/search/posting`
- public detail REST endpoint: `/api/posting/{slug}`

Identity:
- source-local posting slug/id.

Evidence:
- detail JSON is stored as RawObservation.
- category, seniority, requirements, daily tasks, salary and application reference remain source-specific evidence.

### RocketJobs — DIRECT

Transport:
- public SSR listing pages:
  - `/oferty-pracy/wszystkie-lokalizacje`
  - pagination via `?strona=N`
- public SSR detail pages under `/oferta-pracy/{slug}`

Identity:
- canonical detail slug.

Evidence:
- JobPosting JSON-LD is the semantic revision projection.
- rendered HTML remains RawObservation.

The protected `api.rocketjobs.pl` backend is not used.

### Bulldogjob — DIRECT

Transport:
- public English host `bulldogjob.com`, which exposes the same posting IDs as the alternate Polish host.
- listing: `/companies/jobs`
- detail: `/companies/jobs/{numeric-id}-{slug}`

Identity:
- numeric posting ID.

Evidence:
- JobPosting JSON-LD is the semantic revision projection.

The Cloudflare-protected `bulldogjob.pl` interactive surface is not bypassed.

### Pracuj.pl — SECONDARY PUBLIC INDEX

Direct Pracuj surfaces currently return a managed Cloudflare challenge for:
- regular listing pages,
- `it.pracuj.pl`,
- official current-offer sitemap.

No anti-bot bypass is used.

Transport:
- public IsItFair search endpoint.
- only records with `offer_source == pracuj.pl` are accepted.

Identity:
- original Pracuj numeric offer ID parsed from the original `offer_href`.

Provenance:
- source code remains `pracuj` because the observed market posting originates from Pracuj.
- transport is explicitly `public-mirror-isitfair-v1`.
- `observation_provenance = SECONDARY_PUBLIC_INDEX`.
- original Pracuj URL is preserved.
- this evidence must not be treated as equivalent to a direct Pracuj fetch.

## Invariants

- no Cloudflare/WAF bypass;
- source identity and transport identity remain separate;
- no destructive cross-source dedup;
- every posting keeps RawObservation provenance;
- secondary Pracuj observations are distinguishable from direct observations;
- expansion corpus is observational data and does not mutate the frozen ER-EVAL-02 benchmark.

## Scaling after this checkpoint

After the 500-offer corpus is frozen, larger collection should move to scheduled/source-aware acquisition with:
- per-source rate limits,
- incremental manifests,
- checkpointed batches,
- lifecycle-aware recrawls,
- source health metrics,
- durable raw archive/object storage,
- corpus versions rather than replacing prior snapshots.
