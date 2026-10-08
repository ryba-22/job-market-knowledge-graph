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

## AI-first operational extension — 2026-10-08

**The user approved AI-first annotation with humans handling ambiguity, disagreements and an independent control subset.** This does not change the meaning of human gold or release gates. The frozen 200-offer A/B independent-eval protocol remains intact and blocked until independently validated.

### Executed source-only AI pass

- Runner: `.venv/bin/python -m ingestion.classification03_ai --model sonnet --workers 4`
- 200/200 classified using the **full original text**, without CLASSIFICATION-02 labels in prompts. Output was verified individually for posting IDs, source revision/payload hashes, legal family/label values and exact source-quoted evidence; 25/25 batches validated. No API/tool permission was granted to the AI model.
- **AI SILVER / NOT GOLD**: 55 `IT_TECHNICAL`; 111 `NON_IT`; 23 `IT_ADJACENT`; 11 `UNDETERMINABLE`. Confidence: 138 high, 57 medium, 5 low. This is the model's subjective confidence, not calibrated probability.
- Private files: `.local-evidence/classification-03/ai-silver-v1/parts/part-*.json` (source input hash + batch usage), `silver-annotations.jsonl` and `summary.json`. Traceable, individually source-anchored, never merged into human-gold exports.
- CLI-reported cost for 25 batches: USD 1.387. Text was sent to the configured external Claude model for classification; source text and associated details remain in ignored local archives, not committed to public GitHub. Check the job-board data processing/licensing and service-provider retention policy before wider repeated use.

### Human-facing triage

- Offline command: `.venv/bin/python -m ingestion.classification03_triage`.
- Generated **69 source-only human review items**, de-duplicated: 34 AI uncertain/mixed decisions, 6 critical AI-vs-rules differences, 5 low-confidence AI decisions, and 40 fixed stratified random controls. Reasons overlap. 34 distinct cases carry a risk/uncertainty flag, and 29 of those are additional to the 40 random controls (5 overlaps).
- The 40 control cases come from the 160-case probability panel with fixed stratum quotas (12 predicted IT, 12 predicted non-IT, 16 rule-review), selected independently of the **AI SILVER** result. They are not 40 simple random cases from all 509. Broad inference requires appropriate strata weights and uncertainty estimation.
- `.local-evidence/classification-03/silver-human-triage-manifest.json` freezes queue IDs, AI output SHA256 and selection reasons. No silent reshuffle/overwrite if the silver model result changes.
- Open `xdg-open .local-evidence/classification-03/reviewer-human.html`. The display contains only title, category, source link, **complete original description**, and annotation controls. AI labels, confidence, classifier predictions, reasons for prioritization, and gold/holdout information are **not displayed**.
- Export human work to `.local-evidence/classification-03/reviewer-human-annotations.json`, then run `.venv/bin/python -m ingestion.classification03_triage --score-human`. Pending exports, it returns `BLOCKED_NO_HUMAN_REVIEWS`. A partial file reports only checked counts/agreement within the targeted sample; **not unbiased accuracy**.
- Independently reviewing the triage queue is operational QA and improves the next rule iteration. It does **not** by itself unlock the original full 200-offer independent-gold benchmark; that remains `BLOCKED_NO_INDEPENDENT_GOLD`, and no automatic `--freeze-gold` was performed.
- High-risk disagreements are an explicit domain-review gate: do not blindly choose either model's answer. Manual reviewers should independently assess duties first, then adjudicate with side-by-side evidence only after submitting the first label.
- Suggested ownership: one actual reviewer for 69 source-only items; domain adjudicator for six critical disagreements and ambiguous hybrid classes; QA/engineering verify exports and run compare; Ryba approves scope thresholds and GO/NO-GO. A model persona is **not** a separate human reviewer.

## AI reviewer delegation — second pass, domain review, and reduced human queue

Checkpoint: 2026-10-08. User requested delegation of review to the team. The following roles were **implemented as separate AI sessions**, not actual people, independent human annotations, or a goldset:

1. AI reviewer A: 200 original source-only offers (first-pass silver) — complete.
2. AI reviewer B: separate, prediction-blinded source-only classification of all 69 previously flagged offers (Claude Sonnet), 12/12 independently executed batches, 69/69 valid source-linked outputs, USD 0.523 for second pass. Compared with AI A: 59 same labels, 10 different labels (85.51% AI-to-AI agreement; **not accuracy**). Source: `.local-evidence/classification-03/ai-blind-second-v1/`. Runner: `python -m ingestion.classification03_ai_second --model sonnet --workers 3`, compare: `python -m ingestion.classification03_ai_second --compare`.
3. AI domain reviewer C: 12 source-only high-risk cases, the union of 10 inter-AI disputes and 6 critical rule-vs-AI disagreements. An alternate model (Claude Opus) labeled all 12 with verified source excerpts; USD 0.432 for new batch requests. In 11 cases, 2/3 AI opinions agree; one `UNDETERMINABLE` case has 3/3 agreement. **Never accept majority AI vote as human gold, nor equate disagreement with error.** Source: `.local-evidence/classification-03/ai-domain-third-v1/`. Runner: `python -m ingestion.classification03_ai_domain --model opus` and `--compare`.
4. Human priority queue: `40` previously frozen stratified random controls (selected independent of AI outcomes), plus `12` domain-risk cases; overlap `5`; total **47** distinct offers. Full original source text only, no AI labels, predictions, conflicts or control flags in reviewer UI. Run `python -m ingestion.classification03_ai_priority`. Open `.local-evidence/classification-03/reviewer-priority-human.html` in a browser. Export reviewer file to `.local-evidence/classification-03/reviewer-priority-human-annotations.json`, then `python -m ingestion.classification03_ai_priority --score`.

Data contract: The existing full 200-item benchmark and original 69-item review queue are NOT overwritten. The 47-item priority queue is an optional minimized operational slice, not an unbiased replacement for the 200-item independent goldset; its 40 controls are stratified, and the other 7 additional roles are purposively sampled. The same AI family may exhibit correlated mistakes; the independent reviewer identity claim is not true for AI personas. Source hashes and annotation excerpts are revalidated, input packet selection frozen, and model outputs never written to the human-gold files.

**Still blocked:** independent human review of the priority sample; adjudication of policy boundaries; independent quality-evaluation gold labels, confidence intervals and production GO/NO-GO. There is no human-recruiting, task dispatch to actual employees, or production side effect in this checkpoint.

## AI-only delegation of all 47 priority offers — 2026-10-08

User decision: allow the remaining priority review to be performed by AI. This authorizes operational silver review only, NOT independent human gold, production filtering, or changes to original C02 decisions.

The Codex CLI model was checked but unavailable due to a usage-limit block. Instead, the separate source-only Opus reviewer evaluated all 47: 12 pre-existing source-only Opus assessments reused, plus 35 newly evaluated in seven source-bound, verified batches. Fresh reported usage: USD 0.644.

Reproduce: python -m ingestion.classification03_ai_delegate --workers 3 (resumable). Compare: python -m ingestion.classification03_ai_delegate --reconcile.

Private evidence: .local-evidence/classification-03/ai-delegation-v1/ includes frozen run contract, individual batch artifacts, opus-47-annotations.jsonl and ai-silver-proposals.jsonl. The decisions retain original source IDs, revision SHA hashes, three reviewer votes, validated source excerpts and policy-version tags. Public aggregate: reports/classification-03/ai-delegated-47.json.

Three source-only AI opinions on all 47 records: two separate Sonnet sessions, one Opus model session. Two Sonnet sessions may have correlated mistakes. Agreement does not measure truth or generalizable accuracy.

| Provisional AI-silver classification | Count |
|---|---:|
| IT_TECHNICAL | 16 |
| NON_IT | 24 |
| REVIEW_REQUIRED | 7 |

Disposition: 33 unanimous binary AI outcomes; 7 majority (2 of 3) unverified binary decisions; 7 kept in review due to adjacent/undeterminable scope. Three records conflict with confident original rules. No original source/assessment writes.

Quality gate: THREE_AI_SILVER_RECONCILED_HUMAN_GOLD_STILL_BLOCKED. No human labels; no independent-gold quality score; no production GO. The human review UI remains available for future independent verification, but the requested AI-only review has been executed.

Statistical limitation: this 47-case priority queue is enriched for ambiguity and high-risk disagreements, so distribution 16/24/7 is not an unbiased sample of Polish or even Aplikuj-wide IT vacancies.
