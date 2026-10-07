# SCALE-03 retry inventory

Retry-only inventory after run 37642287843.

- durable SOLID successes already preserved: 1,168
- TeamQuest preserved: 124 / 124
- SOLID identities to retry: 2,619
- retry chunks: 11 (max 250)
- reason: 119 parser failures from durable partial chunks + 2,500 identities from chunks 5–14 whose jobs produced no durable artifacts
- parser/evidence fix begins at commit ea10007
