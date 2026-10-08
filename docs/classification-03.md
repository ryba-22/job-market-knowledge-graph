# CLASSIFICATION-03 — independent IT role classification evaluation

Checkpoint 2026-10-08. **CP1 sample/prediction-blind annotation tools: PASS. Independent-gold quality evaluation: BLOCKED, 0/200 labels received.** No crawling or changes to the source archive.

## Source and estimand

- Frozen source: all **509** archived Aplikuj.pl IT-category listing IDs, with immutable source observations (not confirmed currently-active jobs, nor deduplicated vacancies).
- Frozen evaluated classifier: **CLASSIFICATION-02** (`classification-02-rules-v1`), 93 `IT_CONFIRMED`, 149 `NON_IT_CONFIRMED`, 267 `REVIEW_REQUIRED`.
- The category contains software work, infrastructure, data/AI, cybersecurity, teachers, sales, physical telecom installers, PLC/CNC roles, administrative and mixed roles. Technical IT occupation, IT employer, IT industry/category membership and job vacancy are different concepts.
- Classification answers whether **job duties** represent technical IT. Valid gold labels: `IT_TECHNICAL`, `NON_IT`, `IT_ADJACENT` (mixed/outside the strict scope), `UNDETERMINABLE` (source insufficient or contradictory). Gold also records role family, source-anchored quote, and notes.
- Explicit teaching of IT, IT product sales and industrial CNC/robot programming are generally out of narrow *technical software/infrastructure* scope; mixed WordPress/e-commerce, industrial PLC, electronics repair, telecommunications infrastructure, presales and governance-heavy roles need source-based adjudication.

## Sampling design (frozen and reproducible)

200 distinct frozen source IDs, deterministically chosen using a SHA256 sampling seed and archived C02 predictions. **No predictions or model-derived reason codes are included in the annotators' HTML or packets.**

| Panel | N | Composition | Purpose |
|---|---:|---|---|
| Stratified probability sample | 160 | 45 predicted IT; 45 predicted non-IT; 70 previously REVIEW | Precision, recall, prevalence within these 509 category IDs, with inverse selection weights N_h/n_h |
| Adversarial challenge | 40 | Deliberate rare/conflicting/transition titles, excluded from weighted prevalence | Error discovery and stress checks, **not** unbiased population statistics |
| Reserved holdout | 40 | 32 from probability panel, 8 challenge | Inspect only after annotation freeze; never use as tuning data |
| Secondary review | 40 | 32 probability, 8 challenge | Separate independent reviewer (not same ID or same person) |

Sampler manifest (`.local-evidence/classification-03/private-sample-manifest.json`) includes the hidden prior-prediction stratum and locked holdout; the reviewer packets do not. Its SHA256 is in `reports/classification-03/sample-design.json`. Reviewer data is local/private because job advertisements may contain copyrighted text or personal contact details. Only aggregate artifacts are committed.

## End-to-end annotation execution on Ryba

**First reviewer (200 ads)**. In the repository:

```bash
cd ~/job-market-knowledge-graph-scale05
xdg-open .local-evidence/classification-03/reviewer-a.html
```

Reviewer A enters an ID, reads full source duties, chooses a gold scope label and a role family, copies **5–240 source characters** from the specified field for each decisive label, and provides reasons for `IT_ADJACENT` or `UNDETERMINABLE`. For `IT_TECHNICAL`, evidence must come from the **description**, not the title alone. Reviewer explicitly attests to independence, exports a JSON file and retains it. Import that file from within the UI to resume work.

Place the exported JSON at `.local-evidence/classification-03/reviewer-a-annotations.json` (copy/rename the downloaded export; do not edit the original source packet). Annotation state in the browser is temporary until exported.

**Second reviewer (40 ads)** must work independently, without access to A's decisions or C02 predictions:

```bash
xdg-open .local-evidence/classification-03/reviewer-b.html
```

Save the second JSON export as `.local-evidence/classification-03/reviewer-b-annotations.json`. Reviewer IDs must differ. The code checks identities and attestations, but cannot cryptographically prove different humans performed the reviews.

**Score / identify disputes:**

```bash
.venv/bin/python -m ingestion.classification03_score
```

If both sets are complete and disagreement exists, prepare a third independent review:

```bash
.venv/bin/python -m ingestion.classification03_score --prepare-third-reviewer
xdg-open .local-evidence/classification-03/reviewer-c.html
```

Third reviewer exports `reviewer-c-annotations.json` into `.local-evidence/classification-03/` and has a distinct ID. The third packet contains only conflicting source IDs, no model outcomes or A/B decisions. The third verdict resolves disputes. Alternately use explicit, source-validated `adjudications.json` with distinct adjudicator ID. **Do not accept agreement labels copied from model predictions.**

After complete independent assessment:

```bash
.venv/bin/python -m ingestion.classification03_score
.venv/bin/python -m ingestion.classification03_score --freeze-gold
jq '.' reports/classification-03/evaluation.json
```

`--freeze-gold` refuses incomplete/undecided reviews and stores a versioned local fingerprint lock (`gold-freeze.json`). Subsequent changed reviewer files cause fail-closed evaluation, requiring an explicit new checkpoint.

## Quality measurement and release contract

- Before actual independent review, scoring returns **BLOCKED_NO_INDEPENDENT_GOLD**, `metrics=null`, never simulated precision/recall.
- After complete gold, compute precision and recall of `IT_CONFIRMED` against manually verified `IT_TECHNICAL`, with model abstentions (`REVIEW_REQUIRED`) counted as missed opportunities for recall; `IT_ADJACENT` is not accepted as narrow technical IT, `UNDETERMINABLE` excluded from binary denominators.
- Estimate only the sampled **509 source postings** with weights proportional to frozen predicted strata. The 40 purposive adversarial examples remain distinct and unweighted. Report confusion, false confident IT decisions, wrong confident non-IT exclusions of genuine IT, unknowns and holdout results separately.
- Validation checks 200+40 identity/revision/payload hashes; exact quote in original source field; no duplicate labels; distinct reviewers; 40 secondary coverage; all role-family disagreements adjudicated; locked model snapshot; no corrupted gold-freeze.
- The current implementation produces stratified **point estimates, not confidence intervals**. Do not present small decimal variations as statistically reliable or claim market-wide precision without design-consistent uncertainty analysis.
- **No deployment/marketwide count GO** is inferred from a score. The decision owner must approve error tolerances and review manual misclassifications first. A single wrongly excluded confirmed IT job is an escalation candidate.

## Current verified state

- Source archival integrity: PASS, 509/509, no losses.
- CLASSIFICATION-02 decision sidecar: PASS.
- Selection: 200/200 unique, 160 probability + 40 challenge, 40 holdout, 40 double review.
- Reviewer A UI: renders in headless Chrome; Node checks script syntax. Reviewer packet JSON contains no `IT_CONFIRMED`, `NON_IT_CONFIRMED`, `REVIEW_REQUIRED`.
- Independent gold labels: **0/200**. Human evaluation pending. The 64 author-curated diagnostic labels from CLASSIFICATION-02 do **not** qualify as independent gold or holdout.

Source files remain unchanged, current crawlers remain stopped.
