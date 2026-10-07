from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import psycopg

from .model import ParsedPosting, norm_key
from .versions import (
    MATCH_GENERATOR_VERSION,
    NORMALIZER_VERSION,
    ORG_RESOLVER_VERSION,
    PARSER_BUNDLE_VERSION,
)


class PostgresStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def assert_migrated(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                "select to_regclass('public.ingestion_run'), to_regclass('public.schema_migration')"
            ).fetchone()
            if not row or not all(row):
                raise RuntimeError("database is not migrated; run python -m ingestion.migrate first")

    def begin_run(self, run_id: str, *, trigger_kind: str, source_scope: str) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """
                insert into ingestion_run(
                    id, trigger_kind, status, source_scope,
                    parser_bundle_version, normalizer_version
                )
                values (%s,%s,'STARTED',%s,%s,%s)
                on conflict (id) do nothing
                """,
                (
                    run_id,
                    trigger_kind,
                    source_scope,
                    PARSER_BUNDLE_VERSION,
                    NORMALIZER_VERSION,
                ),
            )
            conn.commit()

    def finish_run(self, run_id: str, *, status: str, summary: dict) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """
                update ingestion_run
                set status=%s, summary_json=%s::jsonb, finished_at=now()
                where id=%s
                """,
                (status, json.dumps(summary, ensure_ascii=False), run_id),
            )
            conn.commit()

    def claim_item(self, run_id: str, source: str, source_posting_id: str) -> bool:
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                """
                insert into ingestion_item(run_id, source_code, source_posting_id, status)
                values (%s,%s,%s,'PROCESSING')
                on conflict (run_id, source_code, source_posting_id) do nothing
                returning id
                """,
                (run_id, source, source_posting_id),
            ).fetchone()
            if row:
                conn.commit()
                return True
            existing = conn.execute(
                """
                select status from ingestion_item
                where run_id=%s and source_code=%s and source_posting_id=%s
                """,
                (run_id, source, source_posting_id),
            ).fetchone()
            if existing and existing[0] == "SUCCEEDED":
                conn.commit()
                return False
            conn.execute(
                """
                update ingestion_item
                set status='PROCESSING', error_message=null, finished_at=null
                where run_id=%s and source_code=%s and source_posting_id=%s
                """,
                (run_id, source, source_posting_id),
            )
            conn.commit()
            return True

    def complete_item(
        self,
        run_id: str,
        source: str,
        source_posting_id: str,
        *,
        raw_observation_id: int,
        job_posting_id: int,
    ) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """
                update ingestion_item
                set status='SUCCEEDED', raw_observation_id=%s, job_posting_id=%s, finished_at=now()
                where run_id=%s and source_code=%s and source_posting_id=%s
                """,
                (raw_observation_id, job_posting_id, run_id, source, source_posting_id),
            )
            conn.commit()

    def source_gone_item(
        self,
        run_id: str,
        source: str,
        source_posting_id: str,
        error_message: str,
    ) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """
                update ingestion_item
                set status='SOURCE_GONE', error_message=%s, finished_at=now()
                where run_id=%s and source_code=%s and source_posting_id=%s
                """,
                (error_message[:2000], run_id, source, source_posting_id),
            )
            conn.commit()

    def fail_item(
        self,
        run_id: str,
        source: str,
        source_posting_id: str,
        error_message: str,
    ) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """
                update ingestion_item
                set status='FAILED', error_message=%s, finished_at=now()
                where run_id=%s and source_code=%s and source_posting_id=%s
                """,
                (error_message[:2000], run_id, source, source_posting_id),
            )
            conn.commit()

    def record_attempt(
        self,
        *,
        run_id: str,
        source: str,
        source_posting_id: str,
        requested_url: str,
        attempt_no: int,
        outcome: str,
        failure_type: str | None = None,
        http_status: int | None = None,
        error_message: str | None = None,
    ) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """
                insert into ingestion_attempt(
                    run_id, source_code, source_posting_id, requested_url,
                    attempt_no, outcome, failure_type, http_status, error_message
                )
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (run_id, source_code, source_posting_id, attempt_no)
                do update set
                    outcome=excluded.outcome,
                    failure_type=excluded.failure_type,
                    http_status=excluded.http_status,
                    error_message=excluded.error_message,
                    finished_at=now()
                """,
                (
                    run_id, source, source_posting_id, requested_url, attempt_no, outcome,
                    failure_type, http_status, (error_message or "")[:2000] or None,
                ),
            )
            conn.commit()

    def record_fetch(
        self,
        *,
        source: str,
        url: str,
        final_url: str,
        status: int,
        body: str,
        content_type: str | None,
        run_id: str,
        source_posting_id: str,
        parser_version: str,
        transport_version: str,
        archive_key: str | None = None,
    ) -> int:
        payload_hash = sha256(body.encode("utf-8")).hexdigest()
        archive_key = archive_key or f"{source}/{source_posting_id}/{payload_hash}"
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                """
                insert into raw_observation(
                    source_code, requested_url, final_url, http_status, content_type,
                    payload_sha256, payload_text, run_id, source_posting_id,
                    parser_version, transport_version, archive_key
                )
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (run_id, source_code, source_posting_id, payload_sha256)
                where run_id is not null and source_posting_id is not null
                do update set final_url=excluded.final_url
                returning id
                """,
                (
                    source, url, final_url, status, content_type, payload_hash, body,
                    run_id, source_posting_id, parser_version, transport_version, archive_key,
                ),
            ).fetchone()
            conn.commit()
            return row[0]

    def ingest(self, parsed: ParsedPosting, raw_id: int) -> dict:
        projection = parsed.normalized_projection()
        content_hash = parsed.normalized_hash()
        with psycopg.connect(self.dsn) as conn:
            posting = conn.execute(
                """
                insert into job_posting(source_code, source_posting_id, canonical_source_url)
                values (%s,%s,%s)
                on conflict (source_code, source_posting_id)
                do update set
                    canonical_source_url=excluded.canonical_source_url,
                    last_observed_at=now()
                returning id, current_revision_id
                """,
                (parsed.source, parsed.source_posting_id, parsed.url),
            ).fetchone()
            posting_id, current_revision_id = posting

            previous_hash = None
            previous_projection = None
            if current_revision_id:
                previous_row = conn.execute(
                    "select normalized_content_hash, normalized_projection_json from job_posting_revision where id=%s",
                    (current_revision_id,),
                ).fetchone()
                previous_hash = previous_row[0]
                previous_projection = previous_row[1]
                if isinstance(previous_projection, str):
                    previous_projection = json.loads(previous_projection)

            if previous_hash == content_hash:
                conn.execute(
                    """
                    insert into posting_lifecycle_observation(job_posting_id, raw_observation_id, state)
                    values (%s,%s,'UNCHANGED')
                    """,
                    (posting_id, raw_id),
                )
                conn.commit()
                return {"posting_id": posting_id, "revision_created": False, "state": "UNCHANGED"}

            revision_no = conn.execute(
                "select coalesce(max(revision_no),0)+1 from job_posting_revision where job_posting_id=%s",
                (posting_id,),
            ).fetchone()[0]
            revision_id = conn.execute(
                """
                insert into job_posting_revision
                    (job_posting_id, revision_no, normalized_content_hash, title_source,
                     source_projection_json, normalized_projection_json, raw_observation_id,
                     parser_version, normalizer_version)
                values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                returning id
                """,
                (
                    posting_id, revision_no, content_hash, parsed.title,
                    json.dumps(parsed.source_specific, ensure_ascii=False),
                    json.dumps(projection, ensure_ascii=False),
                    raw_id,
                    PARSER_BUNDLE_VERSION,
                    NORMALIZER_VERSION,
                ),
            ).fetchone()[0]
            conn.execute(
                "update job_posting set current_revision_id=%s, last_observed_at=now() where id=%s",
                (revision_id, posting_id),
            )
            if parsed.company_mention:
                mention_id = conn.execute(
                    """
                    insert into organization_mention(job_posting_revision_id, mention_text, normalized_mention)
                    values (%s,%s,%s)
                    returning id
                    """,
                    (revision_id, parsed.company_mention, norm_key(parsed.company_mention)),
                ).fetchone()[0]
                self._seed_org_candidate(conn, mention_id, parsed.company_mention)
            conn.execute(
                """
                insert into posting_lifecycle_observation(job_posting_id, raw_observation_id, state)
                values (%s,%s,%s)
                """,
                (posting_id, raw_id, "OBSERVED" if revision_no == 1 else "CHANGED"),
            )
            conn.commit()
            changed_fields = []
            change_preview = {}
            if previous_projection is not None:
                keys = sorted(set(previous_projection) | set(projection))
                changed_fields = [k for k in keys if previous_projection.get(k) != projection.get(k)]
                for k in changed_fields:
                    before = previous_projection.get(k)
                    after = projection.get(k)
                    change_preview[k] = {
                        "before": str(before)[:500],
                        "after": str(after)[:500],
                    }
            return {
                "posting_id": posting_id,
                "revision_id": revision_id,
                "revision_no": revision_no,
                "revision_created": True,
                "state": "OBSERVED" if revision_no == 1 else "CHANGED",
                "changed_fields": changed_fields,
                "change_preview": change_preview,
            }

    def _seed_org_candidate(self, conn, mention_id: int, mention: str) -> None:
        key = norm_key(mention)
        org = conn.execute(
            "select id from organization where normalized_name=%s",
            (key,),
        ).fetchone()
        if org is None:
            org_id = conn.execute(
                """
                insert into organization(canonical_name, normalized_name, status)
                values (%s,%s,'CANDIDATE')
                returning id
                """,
                (mention, key),
            ).fetchone()[0]
        else:
            org_id = org[0]
        conn.execute(
            """
            insert into organization_candidate
                (organization_mention_id, organization_id, confidence_band, status, evidence_json, resolver_version)
            values (%s,%s,'LOW','CANDIDATE',%s::jsonb,%s)
            on conflict do nothing
            """,
            (
                mention_id, org_id,
                json.dumps({
                    "epistemic_class": "HYPOTHESIS",
                    "reason": "exact normalized source mention only",
                    "identity_asserted": False,
                }),
                ORG_RESOLVER_VERSION,
            ),
        )
        conn.execute(
            """
            insert into organization_participation
                (organization_id, job_posting_revision_id, role, epistemic_class, confidence_band)
            select %s, om.job_posting_revision_id, 'ADVERTISER', 'FACT', 'MEDIUM'
            from organization_mention om where om.id=%s
            on conflict do nothing
            """,
            (org_id, mention_id),
        )

    def generate_match_candidates(self) -> int:
        with psycopg.connect(self.dsn) as conn:
            rows = conn.execute(
                """
                select p.id, p.source_code, r.normalized_projection_json
                from job_posting p
                join job_posting_revision r on r.id=p.current_revision_id
                """
            ).fetchall()
            created = 0
            for i, a in enumerate(rows):
                for b in rows[i+1:]:
                    if a[1] == b[1]:
                        continue
                    pa, pb = a[2], b[2]
                    if isinstance(pa, str):
                        pa = json.loads(pa)
                    if isinstance(pb, str):
                        pb = json.loads(pb)
                    same_title = norm_key(pa.get("title")) == norm_key(pb.get("title"))
                    same_org = (
                        bool(norm_key(pa.get("company_mention")))
                        and norm_key(pa.get("company_mention")) == norm_key(pb.get("company_mention"))
                    )
                    if not (same_title and same_org):
                        continue
                    x, y = sorted([a[0], b[0]])
                    result = conn.execute(
                        """
                        insert into match_candidate(
                            posting_a_id, posting_b_id, reason_json, status, candidate_generator_version
                        )
                        values (%s,%s,%s::jsonb,'OPEN',%s)
                        on conflict do nothing
                        returning id
                        """,
                        (
                            x, y,
                            json.dumps({
                                "epistemic_class": "HYPOTHESIS",
                                "evidence": ["same normalized title", "same normalized organization mention"],
                                "identity_asserted": False,
                            }),
                            MATCH_GENERATOR_VERSION,
                        ),
                    ).fetchone()
                    if result:
                        created += 1
            conn.commit()
            return created

    def summary(self) -> dict:
        with psycopg.connect(self.dsn) as conn:
            def count(table: str) -> int:
                return conn.execute(f"select count(*) from {table}").fetchone()[0]
            by_source = dict(conn.execute(
                "select source_code, count(*) from job_posting group by source_code order by source_code"
            ).fetchall())
            lifecycle = dict(conn.execute(
                "select state, count(*) from posting_lifecycle_observation group by state order by state"
            ).fetchall())
            return {
                "postings": count("job_posting"),
                "revisions": count("job_posting_revision"),
                "raw_observations": count("raw_observation"),
                "organization_mentions": count("organization_mention"),
                "organization_candidates": count("organization_candidate"),
                "match_candidates": count("match_candidate"),
                "ingestion_runs": count("ingestion_run"),
                "ingestion_attempts": count("ingestion_attempt"),
                "ingestion_items": count("ingestion_item"),
                "by_source": by_source,
                "lifecycle": lifecycle,
            }
