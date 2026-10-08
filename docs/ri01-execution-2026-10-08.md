# RI-01 — executable extraction checkpoint, 2026-10-08

## Decision / state
**PARTIAL IMPLEMENTATION, NO-GO for market assertions.** Do not describe the 200 review candidates as manually labeled ground truth. The experimental HTML viewers are local-only. The crawler remains stopped. No production deploy and no source acquisition.

This checkpoint implements sampling, review queue, baseline evidence extraction, anchor verification, manual-review workbench and local explorer. Independent review, verified gold labels, true precision/recall and source-normalized market estimates are not yet done.

## Inputs and reproducibility
- Canonical read-only input: frozen data/corpora/corpus-10/corpus.jsonl.gz (6,320 source postings, mixed sectors, 10 portals; pinned by data/corpora/corpus-10/manifest.json).
- Code: ingestion/requirement_intelligence.py, ingestion/ri01_review_ui.py, scripts/ri01.py, scripts/ri01_verify.py, scripts/ri01_score.py.
- Reproduction from repo root (existing Python venv):
  - .venv/bin/python scripts/ri01.py
  - .venv/bin/python scripts/ri01_verify.py
  - .venv/bin/python -m pytest tests/test_ri01.py tests/test_ri01_score.py -q
  - After REAL review export: .venv/bin/python scripts/ri01_score.py --review PATH/ri01-reviews.json
- Generated output (ignored by git): .local-evidence/ri01/ including review-packets.jsonl, sample-ids.json, assertion-candidates.jsonl, metrics.json, grounding-qa.json, explorer.html, reviewer.html, review-evaluation.json.
- Rationale for gitignore: excerpts and extended text from third-party listings are not added to a public repository. Code and reproducibility, not verbatim collected material, go into commits.

## CP0 — inspect and source boundary
PASS for frozen corpus identity; BLOCKED for verified IT coverage and job-opportunity deduplication. This experiment does not claim that 6,320 records are distinct Polish IT jobs. 50 of the 200 samples come from metadata-only sources with no extracted assertions. A full source adapter/full lawful detail availability is still needed.

## CP1 — stratified 200-offer review queue
Sampling: deterministic, 10 source quotas, and rotation over title-derived role family, title/portal-derived seniority, heuristic description language. Source split: Bulldogjob 20, IT-Leaders 10, JustJoinIT 20, Michael Page 20, No Fluff Jobs 25, Pracuj 20, RocketJobs 25, SOLID.Jobs 25, TeamQuest 20, TheProtocol 15. The sampling heuristic does NOT certify IT scope, role or language. Intentional inclusion of nontechnical and ambiguous candidates tests false positives. One deterministic identity-based holdout is established; as cross-source opportunity dedup is incomplete, leakage between posting IDs on different boards is possible.

Final execution snapshot: 200 review packets; 156 development, 44 holdout; language candidates EN 80, PL 55, mixed 2, unknown 63. 18 title-family nontechnical, 38 ambiguous; other classes present.

Labeling gate: BLOCKED. 0/200 records have independently confirmed manual gold annotations and 0 have two-reviewer adjudication. Queue and offline reviewer are ready, not completed labels.

## CP2 — first conservative evidence extractor
Candidate numbers for the above sample:
- 150/200 offers with at least one extracted candidate; 50/200 abstain / zero extraction.
- 3,478 candidate assertions: MUST 558, NICE 193, TASK 379, UNKNOWN 2,348.
- No Fluff Jobs: structured must/nice + daily tasks and DOM requirements.
- TheProtocol: typed textSections and expected/optional distinctions.
- JSON-LD: structured HTML section header interpretation with conservative UNKNOWN fallback.
- RocketJobs: plain-text fallback UNKNOWN.
- Missing or flattened portal descriptions cannot be recovered by guessing.
- Each assertion has source ID, revision ID, URL, JSON field path, original quote/DOM segment, candidate classification, mapped concept hints and review state UNREVIEWED.
- A negated statement such as "No Kubernetes experience required" must never become an affirmative MUST; explicit adversarial tests cover this.
- This is a baseline heuristic, not a trained or validated semantic model.

## CP3 — mechanical grounding check
After extraction, independent source-field resolution verifies all 3,478 output quotes against stored structured fields, source arrays or a text projection of the original DOM. Result: 3,478/3,478 mechanically grounded; no failures detected. This is not 100% precision: classification, semantic mapping, completeness and attribution to an independent source remain unverified.

## CP4 — offline review + quality metrics contract
Open .local-evidence/ri01/reviewer.html in a browser that can access the local project directory. Enter reviewer ID, review every candidate as ACCEPT/REJECT, add missed items with exact source quote and modality, check entire available document and export JSON. The exported file is not ingested until explicitly scored. Resumption requires importing the previously exported file; review state is not automatically synced or saved to a server.

scripts/ri01_score.py returns null precision and recall with NO_MANUAL_GOLD and BLOCKED gate until actual complete reviewed labels exist. It verifies candidate coverage and frozen revision IDs in exports, computes TP/FP/manual FN and per-modality counts. Before claiming scientific recall: verify manually added source quotes against original full documents, adjudicate ambiguous labels independently, and verify a stratified gold set. A "reviewed" checkbox alone is not proof of independent correctness.

## CP5 — local Role Capability Explorer
Open .local-evidence/ri01/explorer.html in a browser with access to the project directory. Features: candidate concept counts (unique posting IDs in sample), filter by text/source/family/modality, evidence quote + JSON source path, deep link to original job advertisement. The UI explicitly labels all statistics as candidate-only and not representative market signals. Both standalone UIs have syntactically valid embedded JavaScript according to node --check (browser interaction has not been manually smoke-tested).

## Acceptance / safety constraints
- No broad claims that source posting is a unique recruitment opportunity; repeated postings may inflate counts.
- Do not equate heuristic language / category / title grouping with validated labels.
- Holdout: do not tune rules on holdout reviews; freeze the model version first. Identity split does not prevent cross-board overlap without entity resolution.
- Quality gate proposed in DISCOVERY-RI-01: >=95% explicit must/nice precision and >=95% source anchoring on adjudicated gold; recall and high-risk negative cases measured separately. Not yet assessed.
- No salary-premium estimation, time-series market change claims, AI skill growth conclusions, or self-assessed personal career fit from this experiment.
- Do not publish large third-party descriptions in public dashboards or repository commits without checking rights/retention policy.

## Next executable checkpoints
1. Review data completeness per source; decide whether the metadata-only 50 offers can be used in a modality/recall benchmark or must be replaced by complete-text posts in a new frozen sample version.
2. Freeze a complete review protocol and annotator instructions, manually label 150–200 source-complete offers. Independently double-review at least 20%, adjudicate disagreements, check original full text.
3. Run blind score on held-out, opportunity-deduplicated offers. Investigate per-source modality false positives, missing requirements and knowledge graph normalization.
4. Only then promote an evidence-backed Role Capability Explorer from local candidate explorer to a measured product with truthful denominators and uncertainty.

## Side effects
Only new local extraction/review files, scripts, tests and this documentation. Frozen corpora, source policies, original ingestion worker and crawler state left untouched. Git commit belongs to the existing scale-05-extra-sources branch; push/deploy are independent decisions.
