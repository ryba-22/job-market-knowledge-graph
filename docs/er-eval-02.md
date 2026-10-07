# ER-EVAL-02 — opportunity evidence + adjudication

## Goal

Turn the ER-EVAL review queue into an evidence-backed adjudicated dataset without introducing hand-tuned similarity weights.

## Important repair before adjudication

ORG-02 initially accepted `og-image.justjoin.it` as an organization-domain candidate. That is portal presentation infrastructure, not organization identity.

ER-EVAL-02 rejects the portal root and **all portal subdomains** for Just Join IT and The Protocol before candidate generation.

This is a data-quality repair, not a threshold adjustment.

## Evidence extraction

For each review pair the system inspects the immutable RawObservation used by the current revision and extracts:

- explicit external application URLs,
- ATS URLs and requisition identity,
- explicit requisition/reference fields,
- explicit client wording,
- explicit project wording.

All evidence keeps RawObservation provenance.

## Adjudication policy

### SAME_OPPORTUNITY

Automatic SAME requires decisive shared identity evidence:

- same ATS host + requisition, or
- exact same explicit external application target.

Title, organization-name, location and technology similarity cannot produce automatic SAME.

### DISTINCT_OPPORTUNITY

Automatic DISTINCT requires explicit counter-identity on both sides (for example distinct explicit requisitions).

Different advertiser/company labels alone are not decisive because staffing/recruitment intermediaries exist.

### UNRESOLVED

Everything else stays unresolved.

This is an accepted result. The purpose is a trustworthy benchmark, not forcing all pairs into binary labels.

## Output

- append-only `opportunity_evidence`
- append-only `er_adjudication_decision`
- JSONL and CSV review/eval exports
- strict verification against portal-domain contamination and unsupported auto-labels
