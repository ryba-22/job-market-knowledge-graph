# RI-01 — adjudication protocol v1

## Object of review
Reviewers label an *advertiser statement in context*, never an isolated keyword. Evidence is the exact quoted source text and a versioned location in the archived offer. An inferred skill is not a directly advertised requirement.

## Labels
- MUST: explicit required competency, eligibility constraint, or mandatory qualification. A requirement section establishes modality only when the statement is genuinely required, not negated or conditional.
- NICE: clearly preferred/optional advantage. A tool present in a preferred section must not become MUST.
- TASK: work that the employer expects the hire to perform, including operational ownership, collaboration and deliverables; tasks do not automatically imply mastery of every mentioned tool.
- UNKNOWN: factual mentions, company marketing, benefits, insufficient structure, uncertain conditionality or lack of reliable source context.
- REJECT: extracted statement is not a faithful claim, has a mistaken classification, is duplicated at claim level, or its source excerpt does not support the interpretation.

## Annotation rules
1. Read the full available advertisement and record if the source is incomplete. If missing description is suspected, abstain from recall labeling instead of marking the offer complete.
2. Validate source path and exact text; do not substitute a paraphrase as the evidence quote.
3. Separate multiple independently testable requirements from one sentence where justified, preserving the same exact source quote and explicit concept mappings; do not create unstated obligations.
4. Distinguish candidate level (junior/senior title) from proficiency claim (hands-on, production, leadership). Experience-years are a constraint, not automatically seniority.
5. Capture negation, exceptions, requirements for subsets of candidates, and "willingness to learn" without converting them into unqualified mandatory skills.
6. Do not infer actual organization maturity or use of a practice from the job advertisement.
7. Do not merge roles across companies, recruiters or portals merely on matching employer/title; cross-source opportunity identity is separate work.
8. Review must be exhaustive enough to identify missing advertised statements for recall; explicitly note unavailable full text.
9. Wrong modality: REJECT candidate and add corrected statement in missing list with exact quote and modality.
10. Unknown from source ambiguity remains UNKNOWN or subject to manual review, never default to MUST.

## Reviewer workflow
- Source: .local-evidence/ri01/reviewer.html on the local repo machine.
- One export file per reviewer and round. Export explicitly, then import the previous export to resume; do not assume browser state persists.
- All candidate rows require ACCEPT or REJECT for the record to be marked REVIEWED.
- Missing statements use one row per item: MUST | exact quote ; NICE | exact quote ; TASK | exact quote.
- The reviewer must provide an ID and capture a reason for category ambiguity in notes.
- Never turn a snapshot with unavailable complete descriptions into a positive gold recall sample.
- Baseline development and holdout labels must not leak across tuning cycles.
- Assign at least 20% of source-complete gold postings to a second independent reviewer; adjudicate disagreements before accepting the goldset.

## Quality measures
- Precision: accepted candidate assertions / (accepted + rejected candidates), on fully reviewed postings.
- Recall: accepted assertions / (accepted + manually enumerated missed assertions). If labels have different granularity, harmonize claim splitting before scoring.
- MUST false-positive rate: rejected predicted MUST / all predicted MUST on reviewed postings; separately identify false positive severity (nice -> must, benefit -> must, negated).
- Category/confidence calibration: report per source and role family, not just micro-average.
- Grounding: automatic field resolution and exact DOM-text offsets, followed by manual source verification. Technical grounding alone is not semantic correctness.
- Report eligible N, skipped/partial N, reviewers, disagreements and adjudication procedure along with scores.
- Before release freeze: validate newly added missing quotes against immutable source data and prevent arbitrary free-text from inflating false negatives.
