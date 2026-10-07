# CRAWL-03 — Production ingestion boundary

CRAWL-03 turns the verified CRAWL-02 slice into a restartable and auditable ingestion boundary without adding new sources.

## Contracts

1. Database schema is migrated; application runtime never bootstraps schema.
2. Every execution has a stable `run_id`.
3. Every source item has an idempotency ledger entry scoped by `(run_id, source, source_posting_id)`.
4. Every retry/failure is written to `ingestion_attempt`.
5. RawObservation is immutable evidence and carries run/source identity plus parser and transport versions.
6. Posting revisions carry parser + normalizer versions.
7. Organization and match candidates carry resolver/generator versions.
8. Retry is limited to transient network, HTTP 429 and HTTP 5xx failures.
9. Parser/contract drift and ordinary HTTP 4xx are terminal.
10. Migration checksums are immutable; edited historical migrations fail closed.

## Raw archive contract

The PostgreSQL row is the canonical metadata ledger. Required metadata:
- run_id
- source_code
- source_posting_id
- requested/final URL
- payload_sha256
- parser_version
- transport_version
- archive_key

Payload text remains in PostgreSQL for this version. `archive_key` reserves a stable pointer for an external object store later without changing evidence identity.

## Restart semantics

A successful item in a given run is not executed again when that same `run_id` is replayed. A failed item can be retried under the same run. A new observation cycle uses a new `run_id`.

## Run states

- STARTED
- COMPLETED
- PARTIAL
- FAILED

A run is PARTIAL when at least one item fails but the run still yields useful observations.

## Acceptance

CI must prove:
- migrations are idempotent
- the real 50+50 crawl still succeeds
- replaying the same run produces no duplicate item side effects
- a second run over the exact manifest produces 100/100 UNCHANGED
- transient retry policy is tested
- persisted evidence exposes parser/normalizer/resolver versions
