# RI-01 — model-assisted first annotation, checkpoint 2026-10-08

## Decision and owners
User delegated initial RI-01 annotation work to the AI team so the product owner handles only disputed classifications. Execution: Claude Haiku as first-pass **model proxy** for Jakub (semantic review), independent Claude Sonnet blind review (33 sampled development ads), engineering validation and triage scripts acting under Mariusz engineering responsibilities. These are NOT actual employees or independent human reviewers.

## Frozen scope / side effects
- Decision A manifest: data/evals/ri01-variant-a-selection.json
- Frozen input: data/corpora/corpus-10/corpus.jsonl.gz
- Exactly 161 postings in development; 39 holdout remain SEALED, not visible to either first-pass or second-pass review.
- First-pass and independent review run only on already saved descriptions. No new acquisition, no resumed crawler, no production deployment, no sending messages.
- Job text, model prompts/responses and all candidate-label exports stay under gitignored .local-evidence/ri01/ai-review.
- Public repository stores only code and documentation.

## Executed pipeline
1. scripts/ri01_ai_firstpass.py — Claude Haiku first-pass source-grounded proposals, model-prompt checkpoint per batch, raw response saved before parsing, no automatic replay when raw response exists, no human gold flag.
2. scripts/ri01_ai_secondpass.py — independent blind Claude Sonnet classification of 33 development postings selected by source-balanced sampling; no first-pass labels provided to this model. Comparison reports are advisory, not human evaluation.
3. scripts/ri01_ai_evidence.py — source JSON field path proof and offsets against frozen corpus, beyond assembled page-text substring validation.
4. scripts/ri01_ai_triage.py — cross-check against pre-existing extractor candidate labels, flag unreliable MUST/NICE, negations, questionable short tags (e.g., structured one-letter C), nonexistent verbatim source quotes, model/extractor conflicts.
5. scripts/ri01_ai_disputes_ui.py — local HTML with P0/P1 issues and exportable operator decisions (never auto-applied to goldset).
6. tests/test_ri01_ai_review.py — synthetic tests of checkpoint replay safety, ungrounded flagging and escaping of source data.

## Reproducibility, local-only
From the repository root:
- .venv/bin/python scripts/ri01_ai_firstpass.py --parallel 4
- .venv/bin/python scripts/ri01_ai_secondpass.py --parallel 2
- .venv/bin/python scripts/ri01_ai_evidence.py
- .venv/bin/python scripts/ri01_ai_triage.py
- .venv/bin/python scripts/ri01_ai_disputes_ui.py
- .venv/bin/python -m pytest -q

First-pass runner recovers already persisted responses without rerunning paid inference. It validates SHA-256 of its prompt before accepting preexisting batch checkpoints. Failed batch parsing must be reconciled from saved RAW before retrying requests. The second-pass runner similarly reuses preexisting result batches. Keep model source material separated from outside instructions.

## Evidence and quality policy
- AI annotations are MODEL_DRAFT_UNVERIFIED; do NOT inject them as human reviewer export or manually adjudicated gold.
- Exact source quote check can fail because a generative model paraphrased or output changed punctuation; keep those candidates for review, not counted as grounded.
- Source-field grounding is mechanical only and may still support an incorrect modality; model-to-model agreement is NOT precision or recall.
- Source IT classification, employer opportunity entity-resolution, model false-negative recall and human label quality remain unvalidated.
- Model Haiku first-pass is selective, not exhaustive; proposed recall metric is BLOCKED.
- Holdout evaluation requires an independent sealed goldset and no tuning based on holdout.
- Codex CLI was unavailable because the account had reached its usage limit. A separate Claude Sonnet run was performed instead.

## Manual decision boundary
Open the local dispute queue HTML only after running the triage and renderer. Review P0 first. Confirm or reject each proposal with exact original source context. Export reviewer decisions and run a separate adjudication/validation process before any label can be promoted to gold. Human reviewer, inter-reviewer adjudication and final benchmark remain NOT DONE.

## Critical observed examples
- Neontri Product Owner: structured NoFluff metadata contains bare C as MUST; the description actually asks for experienced PO, roadmapping, Jira/Confluence and English. The label C needs rejection or source clarification, not assumption of C programming expertise.
- TheProtocol Senior Test Automation Engineer: "ISTQB certified or at least concepts are known" is a conditional alternative, not straightforward required certification; a responsibilities sentence also mixes previous finance-industry testing experience with partial project ownership.
- Spyrosoft SDN Engineer: production experience with OVS/OVN is explicit in prose but a previous baseline marked it UNKNOWN.

## Gates
First-pass model labeling: model draft artifact only, not gold.
Independent second-model crosscheck: advisory only, not human.
Source grounding: separate mechanical QA report.
Human gold / independent human adjudication / precision / recall: BLOCKED until a human-reviewed labeled sample exists.

## Final measured artifact counts at this checkpoint
- First-pass Claude Haiku: **161/161 development offers**, 1,549 proposed statements (MUST 1,034; NICE 154; TASK 358; UNKNOWN 3). Exact quote present in assembled review text: 1,462, unanchored 87.
- Stricter independent archive-field grounding: 1,458/1,549 have resolvable archived source field/path and exact text; 91 unresolved; at least one grounded assertion on 160 postings. This is only technical evidence validity, not semantic validity.
- Independent blind Claude Sonnet: **33/161 development offers (20.5%)**, 315 proposed statements, 307 anchored in review text, 8 not; 112 exact-shared quotes have same label, 4 exact-shared quotes disagree. Statements that differ in span or wording are not included in this comparison; agreement is NOT correctness/precision.
- Model-vs-extractor triage generated 878 advisory observations. Source/label QA queue: **99 actionable items**. Informational candidate-label promotions relative to the baseline UNKNOWN: 771, all unverified.
- Business escalation is intentionally limited to **13 unresolved domain cases**, in .local-evidence/ri01/ai-review/escalation-queue.jsonl and the local disputes.html interface.
- 39 holdout postings never entered first- or second-pass model prompts.
- Actual human-reviewed/adjudicated gold labels: **zero**. Accuracy, precision, recall, false-MUST rates remain UNMEASURED / NO-GO.

## Operational file locations
- Model drafts: .local-evidence/ri01/ai-review/ai-firstpass.jsonl
- Source-field-grounded view: .local-evidence/ri01/ai-review/ai-evidence-verified.jsonl
- Blind second-model results: .local-evidence/ri01/ai-review/sonnet-crosscheck/second-model-claims.jsonl
- Human-review escalations: .local-evidence/ri01/ai-review/disputes.html (open locally)
- Technical QA queue: .local-evidence/ri01/ai-review/qa-queue.jsonl
- Full audit counts: firstpass-status.json, ai-field-grounding.json, escalation-status.json, sonnet-crosscheck/status.json.

A manually entered decision from disputes.html is not applied by itself. It requires an exported review file, source verification and subsequent goldset adjudication. No paid model request was repeated after batch JSON format errors: batches 97, 105 and 145 were recovered from previously saved raw responses.
