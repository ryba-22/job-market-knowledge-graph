# DISCOVERY-RI-01 — Requirements & Work Intelligence, 2026-10-08

## Scope and execution
Read-only inspection of existing frozen job-offer data and current repository contracts; no crawling resumed, no production deployment, no changes to existing parsers. This is a discovery proposal, NOT an implemented extraction pipeline. Review is synthesized across business/product (Ryba), domain/architecture (Jakub), and engineering/data (Mariusz) perspectives; it is NOT their independent sign-off.

Sources inspected: README.md, docs/analysis-method.md, schema/job-analysis.schema.json, reports/market-snapshot.md, docs/it-market-discovery-2026-10-08.md, data/corpora/corpus-10/manifest.json, corpus-10/corpus.jsonl.gz, selected normalized records. External references: ESCO API, O*NET content model, Lightcast skill taxonomy, OECD online vacancy data methodology.

## Verified facts
- CORPUS-10 frozen: 6,320 postings from 10 source systems; 3,235 solidjobs; 650 each nofluffjobs, justjoinit, rocketjobs; 463 bulldogjob; 368 michaelpage; 124 teamquest; 120 pracuj; 50 theprotocol; 10 itleaders. It is a mixed, not IT-classified, not opportunity-deduplicated corpus.
- In a bounded read-only full scan over CORPUS-10 (heuristic field extraction, counts NOT quality claims): 6,072 records yielded >=100 characters of candidate description/sections; 5,935 >=500 characters; 3,773 >=1,500 characters; 5,083 showed potentially usable salary metadata. Text availability != skill evidence correctness; pay metadata != normalized comparable offers.
- No Fluff Jobs (650 records): 644 nontrivial requirements descriptions, 637 nonempty 'musts', 352 nonempty 'nices', 612 nonempty explicit dailyTasks, 77 nonempty methodology arrays. Other sources frequently expose a JSON-LD JobPosting description rather than structured must/nice lists.
- Current knowledge graph pipeline is essentially a single hand-curated seed: reports/market-snapshot.md says "Analyzed offers: 1"; the schema does NOT contain requirement-level anchored provenance, modality, source span, classification confidence, or semantic-proficiency qualifiers.
- Discovery-IT-02 separately confirms source-count/candidate-count/deduplicated-opportunity-count cannot be equated, regional scopes vary, and existing crawler queues were paused by user. Do NOT restart them as part of this work.

## Fundamental distinction
Posting != vacancy != unique recruitment opportunity. Keyword mention != requirement. Requirement != competency. Responsibility != tool. Employer statement != observed engineering practice. Absence of a skill in a posting != skill unnecessary. Salary association != causal premium. Publication date != hire/closure date. Extracted claim != verified claim.

## Product opportunities (prioritization proposals, not validated demand)

| Rank | Intelligence product | Questions answered | Confidence and dependency |
|---|---|---|---|
| P0 | Evidence-backed requirement atlas | What exact must/nice, skill depth, languages and experience are requested by role? | High value; full text + source spans + annotation |
| P0 | Role/capability/responsibility graph | What must an engineer be able to DO, own, and demonstrate? | High; sentence-level ownership extraction |
| P1 | Skill bundle / co-occurrence graph | Which capabilities and technologies appear together in the same recruitment? | Requires dedupe + IT scoping + careful denominators |
| P1 | Role archetypes and title drift | Is an 'Architect' an operator, integrator, hands-on builder, people leader, or governance owner? | Needs multiple role dimensions and human-validated cluster names |
| P1 | Seniority by accountability | Does the role require implementation, production ownership, incident response, decision leadership, mentorship? | Need proficiency/depth labels, separate advertised seniority |
| P1 | Problem & system-pressure radar | Legacy modernization, integrations, compliance, performance, reliability, AI adoption, cost? | Some explicitly stated, others inferred; never blur |
| P1 | Engineering operating-model map | CI/CD, release cadence, code review, QA ownership, on-call, SRE, security collaboration? | An advertisement describes desired work, not verified organization maturity |
| P1 | Portfolio proof planner | What artifacts and tests could demonstrate capabilities requested by real ads? | Match assessed abilities/projects with claims and evidence; never claim auto-proven fit |
| P2 | Compensation / contract / location comparator | How does salary correlate with role, evidence depth, geo, employer, tech stack? | Need wage standardization, gross/net/B2B/contract/hours, selection-bias controls |
| P2 | Demand change and new stack signals | Which requirements increase across independent employers over time? | Requires recurring comparable snapshots, dedupe, coverage normalization |
| P2 | Career transition graph | Which capabilities transfer from backend -> platform -> staff/architect/AI engineering? | Graph recommendation is a hypothesis, not proof of employability |
| P2 | Training syllabus / learning ROI analyzer | Which unmet capabilities yield broadest advertised opportunity coverage per effort? | Requires ground-truth user skills, learning cost and noncausal outcome framing |
| P3 | Hiring market friction | Long-lived vacancies, reposting, agency cross-posting, title inflation? | Listing lifetime/reposting are weak proxies; do not infer failure-to-hire |
| P3 | Labor market segmentation / recruiter map | Direct employer vs agency, sector, product vs consulting, geographic and remote eligibility | Need verified employer identity and recruiter/hiring-company separation |

## Proposed domain model
1. PostingObservation: source, source_posting_id, retrieved_at, revision_id, raw hash, parsed document version, original URL and source-specific fields. Immutable.
2. RecruitmentOpportunity: potential de-duplicated employer requisition, with confidence, supporting and contradicting evidence; MAY map multiple source postings. Identity is not a title.
3. RequirementAssertion: occurrence at exact source span / structured JSON path; verbatim quote; category (technology, capability, process, responsibility, constraint, language, experience, domain, qualification); statement type (MUST, NICE, TASK, BENEFIT, CONTEXT, UNKNOWN); depth (awareness, working, production, leadership, unspecified); qualifiers (years, scope, conditional requirements); negation; assessment confidence; reviewer adjudication.
4. Concept: canonical meaning, aliases, taxonomy version, related ESCO/O*NET/Lightcast IDs where licensing permits; distinguish technology from competency and operation.
5. Responsibility/Problem/QualityAssertion: explicit vs inferred assertions about work to be done, desired system properties and collaboration. Inferred edges have separate support and confidence, never masquerade as advertisement facts.
6. MarketSignal: aggregation over a stable population and time window; method-versioned filters, sources, numerator/denominator, dedupe policy, uncertainty intervals, data coverage, evidence drilldown.
7. PersonalEvidence: independent portfolio/work samples/verified capability levels; NEVER extracted automatically as proof from a vacancy.

### Example anchored extraction from the previously inspected No Fluff Jobs listing OXM6CYW3
- source text: "Experience with distributed systems, microservices, and API design."
- claim: technical competency, explicit required section, source quote and document path, three mapped concepts (distributed systems, microservices, API design), no unmentioned Kubernetes requirement.
- separate 'nice' text: Docker/Kubernetes is preferred, not mandatory.
- business problem ("open source architecture aligning business goals") is a supported interpretation, stored separately from literal claims.

## Quality / reliability gates
- Population contract FIRST: technical IT vs IT-adjacent vs NON-IT vs REVIEW; geography and remote eligibility; agency vs hiring company; status as-of-time.
- Make one source-specific extraction adapter per family (NFJ structured requirements, JSON-LD descriptions, source-specific detail records) and one consistent domain result.
- Annotate an initial 150-200 offers stratified by source, job family, seniority and language; include hard negative, empty sections, contradictory requirements, repeated posts, marketing prose, multi-role ads. Double-review ~20% and adjudicate.
- Measure separately: source-text availability, correct must/nice classification, span grounding, entity/concept mapping, ownership/quality classification, missed implicit requirements, false positives, abstention and duplicates.
- Proposed gate (decision still open): >=95% precision on explicit must/nice, >=95% extracted claims anchored to genuine supporting spans, no critical cross-category/negation errors in the gold set. Track recall too; do not optimize precision alone. Underperforming categories yield REVIEW_REQUIRED.
- Freeze annotation and taxonomy versions; compare baseline rules vs LLM extraction vs hybrid; independent eval on held-out posts; version prompting/model/policy and track cost/post.
- Salary analytics is blocked until compensation periods/units and employment contracts normalize correctly. Temporal trend analytics is blocked until comparable follow-up capture exists.
- Protect copyrighted job-description text: use evidence excerpts minimally in external UIs, link to the original, maintain source policies; validate licensing separately.

## Product slice / executable checkpoints
CP0 INVENTORY: freeze source manifest and extraction-ready population without restarting crawlers. PASS = per-source usable text, IT scope and source caveats reproducible.
CP1 GOLDSET: label 150-200 posts with exact spans and modality, representative/adversarial; reviewers adjudicate disagreements. PASS = repeatable eval set.
CP2 EXTRACT: source-specific evidence extraction -> RequirementAssertion for 3 source families. PASS = correct source references, no fabricated assertions; explicit abstention.
CP3 NORMALIZE: typed concepts and role/accountability categories, versioned aliases, external taxonomy linkage if lawful. PASS = accepted normalization parity + human review.
CP4 LINK: deduplicate opportunities, distinguish postings and opportunities, connect assertions with ownership and work context. PASS = candidate recall evaluated, merges traceable and reversible.
CP5 FIRST PRODUCT: an evidence-driven Role Capability Explorer, drill-down from aggregated requirement to exact source/quote, filter by role/seniority/location/time. PASS = source-grounded counts and uncertainty visible.
CP6 ADVANCED ANALYTICS: skill bundles, role archetypes, problem radar, portable career pathways; only then compensation analysis and time trends with their own gates.

## External anchors
ESCO: https://esco.ec.europa.eu/en/use-esco/use-esco-services-api/esco-web-service-api
O*NET Content Model: https://www.onetcenter.org/content.html
Lightcast Skills: https://lightcast.io/taxonomies/skills-taxonomy
OECD caveats on online job postings: https://www.oecd.org/en/publications/skills-for-the-digital-transition_38c36777-en/full-report/component-5.html

## Open questions
- Is the primary user a candidate building personal portfolio, an IT hiring manager, a curriculum designer, or a market analyst? Product priorities differ.
- Should the product focus on technical IT Poland only, or separate Poland-eligible remote/global analysis?
- Which seniority/depth rules are acceptable, especially for vague labels such as 'expert'?
- How should direct employer, recruiting agency and client company be represented to prevent repeated requisitions from biasing signals?
- What is the sustainable lawful retention/citation policy for employer text?
- What are the allowed inference levels for problem/organizational maturity claims?
- Should the first alpha be source-specific (NFJ quality-first) or stratified across source families (coverage-first)?

## Decision proposed
Start with an evidence-backed RequirementAssertion and Capability Explorer, not a generic dashboards/LLM summaries product. Use an adjudicated evaluation set to disprove the current model before scaling. Hold salary premium, trend and hiring friction claims until population/identity/temporal contracts are verified.
