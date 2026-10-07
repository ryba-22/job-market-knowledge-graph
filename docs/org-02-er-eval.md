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


---

# ORG-02 + ER-EVAL — verified real-corpus results

Date: 2026-10-07  
Workflow: `ORG-02 + ER-EVAL #3`  
Corpus: 100 current postings (50 The Protocol + 50 Just Join IT)

## Verification

CI: **PASS**

```
tests                         PASS
migrations                    PASS
real 100-posting ingestion    PASS
ORG-02 enrichment             PASS
ER-EVAL corpus generation     PASS
strict verifier               PASS
evidence upload               PASS
```

## ORG-02

Observed:

```
organization mentions     100
mention evidence          100
explicit URL evidence      62
domain candidates          62
verified domains            0
total organization evidence 162
```

Interpretation:

- every source organization mention has provenance-backed evidence,
- 62 postings exposed an explicit URL/domain-bearing organization signal,
- those domains remain `CANDIDATE`, not `VERIFIED`,
- no corporate domain was guessed from a company name,
- no source display company was promoted automatically to EMPLOYER or END_CLIENT.

The result supports the ORG-01 distinction:

`OrganizationMention != Organization != OrganizationParticipation`.

## ER-EVAL

The first generator pass produced:

```
postings considered         100
candidate pairs              16
review pairs                 16
AUTO SAME                     0
AUTO DISTINCT                 0
UNRESOLVED                   16
```

Strata:

```
org_legal_suffix_variant_exact_title   1
similar_title_cross_org               15
```

The legal-suffix case was discovered empirically:

```
Ness Solution sp. z o.o.
vs
Ness Solution

title:
Test Automation Engineer
vs
Test Automation Engineer
```

The resolver now treats legal-form normalization only as **candidate-generation evidence**. It does not merge organizations or assert opportunity identity.

## Important falsifications

### F-01 — Exact title similarity is noisy

Pairs such as:

```
Java Developer ↔ Java Developer
Business Analyst ↔ Senior IT Business Analyst
IT/OT Security Engineer ↔ IT Security Engineer
```

occur across unrelated organization mentions.

Therefore title similarity is useful for candidate generation, not identity.

### F-02 — Different source organization labels do not prove distinct opportunity

Recruitment/staffing/intermediary cases mean:

`different advertiser != decisive DISTINCT_OPPORTUNITY`.

The evaluator correctly keeps those pairs unresolved without project/client/ATS evidence.

### F-03 — Same organization name after legal-suffix normalization is not decisive SAME evidence

`Ness Solution sp. z o.o. ↔ Ness Solution` is a much better candidate than generic title similarity, but still requires opportunity-level evidence.

### F-04 — Current 100-posting sample contains no decisive identity evidence

No pair in this sample exposes enough evidence for an honest automatic:

- `SAME_OPPORTUNITY`, or
- `DISTINCT_OPPORTUNITY`.

This is a valid research result. Thresholds must not be weakened merely to manufacture positive labels.

## Current benchmark status

ER-EVAL now has a reproducible **review corpus**, not yet a calibrated ground-truth benchmark.

Next stage:

```
16 review pairs
→ evidence expansion (project/client/application/ATS)
→ human/adjudicated labels
→ SAME / DISTINCT / UNRESOLVED
→ candidate recall measurement
→ only then score/threshold calibration
```

No production similarity weights should be introduced before that adjudicated dataset exists.
