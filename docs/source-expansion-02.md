# SOURCE-EXPANSION-02 — Bulldogjob

Current public source domain: https://bulldogjob.com

## Discovery
Public listing: https://bulldogjob.com/companies/jobs

Observed listing exposes 100 distinct active job URLs in the initial SSR response.
robots.txt also advertises https://bulldogjob.com/sitemap.en.xml.gz.

Source-local identity is the numeric job id at the start of the detail URL tail.

## Detail semantics
The public detail page exposes JobPosting JSON-LD with title, responsibilities, requirements, skills, hiring organization, locations, employment type and lifecycle dates.

No WAF bypass or private API is used.

## Acceptance
- at least 95 distinct Bulldogjob postings
- unique numeric source identities
- immutable RawObservation provenance
- compact frozen source corpus with checksums
