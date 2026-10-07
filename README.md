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
