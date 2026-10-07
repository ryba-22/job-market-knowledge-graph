# SCALE-04 — additional direct-source inventory

Frozen on 2026-10-07.

Scope:
- Aplikuj.pl / IT-Informatyka: 522 current listing identities
- IT-Leaders: 10 current listing identities
- Michael Page Poland / Information Technology: 86 current listing identities

Total: 618 identities.

Discovery semantics:
- Aplikuj: only anchors from the IT/Informatyka listing (`a.offer-title`), excluding repeated sidebar/promoted links.
- IT-Leaders: current SSR listing. `?page=2` returns the same identity set, so the current-list universe is 10.
- Michael Page: `/en/jobs/information-technology/poland`, pages 0..2; page 3 returns 404. Source identity is the `JN-*` reference.

All three are direct-source observations. Michael Page is a recruiter/agency source, so advertiser identity must not be treated automatically as the end employer.
