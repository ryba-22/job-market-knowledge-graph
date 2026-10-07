# SOURCE-EXPANSION-01

Goal: broaden the durable job-market corpus beyond Just Join IT and The Protocol.

## Source archaeology

### No Fluff Jobs — ingestion approved

Public transport:
- POST https://nofluffjobs.com/api/search/posting
- GET https://nofluffjobs.com/api/posting/{slug}

Observed search contract:
- query: salaryCurrency=original
- query: salaryPeriod=original
- query: region=pl
- body: {"criteriaSearch": {}}

One observed search response exposed 134 current postings, with stable slug/id, company, title, salary, category and location metadata.

Detail JSON exposes:
- title
- company
- requirements
- methodology
- recruitment
- location
- salary/contracts
- apply/reference
- posting status
- version
- expiry

### RocketJobs — ingestion approved

Public discovery:
- robots.txt advertises https://rocketjobs.pl/sitemaps/active-jobs.xml
- active-jobs sitemap index points to active job sitemap parts
- observed part contained >15k active job URLs

Detail transport:
- public SSR detail page
- stable JobPosting JSON-LD
- hiringOrganization
- description
- location
- employmentType
- datePosted
- validThrough

No direct API dependency is required.

### Pracuj.pl — TRANSPORT_BLOCKED

Public listing/detail/sitemap HTTP requests from the automated client currently return Cloudflare challenge/403.

robots.txt advertises CurrentOffers and search sitemaps, but fetching those paths still triggers the challenge.

Decision:
- do not bypass Cloudflare
- do not emulate challenge solving
- retain source as research-known but ingestion-blocked until a stable public/official transport is identified

### Bulldogjob — TRANSPORT_BLOCKED

Public automated HTTP requests currently return Cloudflare challenge/403.

Decision:
- do not bypass Cloudflare
- retain source as research-known but ingestion-blocked until a stable public/official transport is identified

## Acceptance

SOURCE-EXPANSION-01 succeeds when:
- at least 95 NFJ current postings are ingested
- at least 95 RocketJobs current postings are ingested
- all records retain source-local identities and RawObservation provenance
- compact source corpus is exported with checksums
- no WAF bypass is introduced
