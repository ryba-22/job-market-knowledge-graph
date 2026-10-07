# Metoda analizy ofert

## 1. Problem, który firma próbuje rozwiązać
Nie zaczynaj od technologii. Odtwórz system odpowiedzialności:
- co ma działać,
- dla kogo,
- pod jakim obciążeniem,
- jakie awarie są istotne,
- kto jest właścicielem wyniku.

## 2. Evidence extraction
Z ogłoszenia wyciągaj osobno:
- role i poziom,
- odpowiedzialności,
- technologie,
- procesy/praktyki,
- artefakty operacyjne,
- wymagane doświadczenie,
- słowa kluczowe,
- współpracujące zespoły,
- constraints i quality attributes.

## 3. Normalizacja
Mapuj synonimy do kanonicznych pojęć, np.:
- K8s → Kubernetes
- OTel → OpenTelemetry
- incident management / troubleshooting / RCA → Reliability / Incident Response
- model deployment / hot swap / rollback → Model Lifecycle Management

## 4. Graf
Preferowane typy węzłów:
ROLE, CAPABILITY, RESPONSIBILITY, PROCESS, TECHNOLOGY, PRACTICE,
QUALITY_ATTRIBUTE, ARTIFACT, DOMAIN, TEAM, KEYWORD.

Preferowane relacje:
ROLE_REQUIRES_CAPABILITY
ROLE_OWNS_RESPONSIBILITY
RESPONSIBILITY_USES_TECHNOLOGY
RESPONSIBILITY_REALIZED_BY_PROCESS
PROCESS_SUPPORTED_BY_TECHNOLOGY
TECHNOLOGY_SERVES_CAPABILITY
CAPABILITY_SUPPORTS_QUALITY_ATTRIBUTE
ROLE_COLLABORATES_WITH_TEAM
OFFER_MENTIONS_NODE
CONCEPT_ADJACENT_TO_CONCEPT

## 5. Ocena pod kątem rozwoju
Dla każdego istotnego obszaru:
- current_fit: strong / medium / weak / unknown
- evidence_level: demonstrated / practiced / conceptual / none
- market_signal: isolated / recurring / cluster-forming
- learning_value: low / medium / high
- portfolio_candidate: true/false

## 6. Słowa kluczowe
Nie tylko lista ATS. Każde słowo klasyfikuj:
- tool,
- platform,
- process,
- architecture,
- reliability,
- security,
- data/AI,
- delivery,
- business/operating-model.

## 7. Pytania falsyfikujące
- Czy technologia jest rdzeniem odpowiedzialności, czy tylko dodatkiem?
- Czy wymaganie jest produkcyjne, czy wystarczy familiarity?
- Czy dwa słowa opisują ten sam capability?
- Czy firma szuka operatora platformy, twórcy produktu, czy integratora?
- Czy częstotliwość technologii rośnie w wielu niezależnych ofertach?
- Czy luka jest naprawdę technologiczna, czy dotyczy production evidence?

## 8. Wynik pojedynczej analizy
Analiza kończy się:
1. mental model roli,
2. macierzą technology/process/ownership,
3. grafem nowych relacji,
4. delta wiedzy względem poprzednich ofert,
5. hipotezami o rynku,
6. rekomendowanymi eksperymentami edukacyjnymi.
