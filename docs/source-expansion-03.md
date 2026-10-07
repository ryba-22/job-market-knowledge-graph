# SOURCE-EXPANSION-03 — Pracuj secondary index and CORPUS-05

## Boundary

Direct Pracuj listing, IT surface and official current-offer sitemap return a managed Cloudflare challenge to the automated client.

No challenge bypass is used.

The checkpoint uses the public IsItFair search index only for records whose upstream offer_source is exactly pracuj.pl.

## Identity and provenance

- source: pracuj
- source identity: numeric Pracuj offer ID parsed from the original Pracuj URL
- original Pracuj URL retained
- transport: public-mirror-isitfair-v1
- observation provenance: SECONDARY_PUBLIC_INDEX
- direct source access: false

Secondary records must never be treated as evidence-equivalent to a direct Pracuj observation.

## Target

Add 75 current Pracuj observations to frozen CORPUS-04:

- CORPUS-04: 493
- Pracuj secondary: 75
- CORPUS-05 target: 568

## Scale implication

Larger acquisition should remain incremental: collect new/versioned slices and combine immutable corpus versions instead of recrawling all previous sources for every checkpoint.
