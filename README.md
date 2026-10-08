# Job Market Knowledge Graph

Repozytorium do systematycznej analizy ofert pracy jako źródła wiedzy o rynku technologii, procesach inżynierskich, odpowiedzialnościach i rolach.

## Cel

Nie kolekcjonujemy ofert. Budujemy graf:
`rola → odpowiedzialność → capability → proces → technologia → praktyka → problem → evidence`.

Każda oferta:
1. zostaje zapisana jako evidence,
2. jest analizowana według wspólnego kontraktu,
3. dodaje lub wzmacnia węzły i relacje w grafie,
4. aktualizuje sygnały rynkowe i mapę luk kompetencyjnych,
5. może wygenerować eksperyment edukacyjny lub projekt portfolio.

## Struktura

- `data/jobs/` — znormalizowane analizy pojedynczych ofert
- `knowledge/nodes.jsonl` — węzły grafu wiedzy
- `knowledge/edges.jsonl` — relacje między węzłami
- `docs/analysis-method.md` — metoda analizy
- `schema/job-analysis.schema.json` — kontrakt danych
- `scripts/build_graph.py` — agregacja grafu i snapshot rynku
- `reports/` — generowane przekroje
- `tests/` — walidacja agregacji

## Zasada epistemiczna

FACT ≠ INTERPRETATION ≠ DECISION.

Oferta może potwierdzić, że firma wymaga Kubernetes. Nie potwierdza sama w sobie, że Kubernetes jest najlepszą inwestycją dla konkretnej osoby.

## Pierwszy seed

T-Mobile / T-Hub — AIOps Engineer — AI Infrastructure & Orchestration, 2026-10-06.

## RI-01 — evidence-backed requirements extraction (experimental)

The offline baseline extracts source-linked candidate requirements, responsibilities and concept hints from frozen CORPUS-10 without resuming crawlers. It includes a reproducible 200-offer review queue, a local review workbench and a local Role Capability Explorer. Candidate labels are **not** verified ground truth; manual adjudication and quality gates remain open.

See docs/ri01-execution-2026-10-08.md and docs/ri01-annotation-guidelines.md for commands, constraints, outputs, evaluation and next checkpoints. Variant A was executed and frozen: see docs/ri01-variant-a-2026-10-08.md, with the 200-ID selection manifest at data/evals/ri01-variant-a-selection.json. The local reviewer covers 161 development postings; the 39-item holdout is kept separate. Evidence outputs with third-party advertisement excerpts remain in ignored .local-evidence/ri01/.

Model-assisted RI-01 review (not human gold): see docs/ri01-ai-annotation-2026-10-08.md. A first model proposed source-anchored labels for all 161 development postings, while a second model blindly reviewed 33. The local domain dispute queue is in .local-evidence/ri01/ai-review/disputes.html; unresolved technical source checks are separated. Holdout remains sealed and precision/recall remain unmeasured.
