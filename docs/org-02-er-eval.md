# ORG-02 + ER-EVAL — real-corpus checkpoint

## Scope

This checkpoint consumes the verified 50 The Protocol + 50 Just Join IT corpus.

It does **not** add new sources and does **not** auto-merge postings.

## ORG-02

ORG-02 upgrades the seed organization model from:

`source label → LOW-confidence OrganizationCandidate`

to evidence-backed organization resolution inputs.

It stores:
- source organization mention as FACT,
- explicit organization/profile/careers URL when the source actually exposes one,
- explicit domain candidate derived from that URL,
- provenance path, source posting identity and revision,
- resolver version.

It does not:
- guess a corporate domain from organization name,
- treat portal display name as legal employer,
- infer unnamed end client,
- mark domains VERIFIED without independent evidence.

## ER-EVAL

ER-EVAL creates a reproducible cross-source review corpus from the 100 real postings.

Candidate generation uses blocking/strata, not identity assertions:
- same organization mention + exact title,
- same organization mention + similar title,
- same organization candidate + similar title,
- shared explicit organization domain,
- sufficiently similar title across different org mentions.

Every pair stores:
- source identities,
- feature vector,
- evidence vector,
- stratum,
- generator version,
- proposed label and label basis.

### Label policy

`SAME_OPPORTUNITY` may be assigned automatically only from decisive identity evidence such as a shared canonical employer posting or ATS requisition.

`DISTINCT_OPPORTUNITY` may be assigned automatically only from decisive counter-evidence such as incompatible explicit requisition identities.

v1 does **not** currently invent either of those from title/company similarity.

Therefore a valid result can contain many or all pairs as `UNRESOLVED`. That is evidence that human/adjudicated labels are still required, not a benchmark failure.

## Next calibration step

A reviewer labels the exported corpus:
- SAME_OPPORTUNITY
- DISTINCT_OPPORTUNITY
- UNRESOLVED

Only after that labeled benchmark exists should scoring weights or ML similarity thresholds be calibrated.
