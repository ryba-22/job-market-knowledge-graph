from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import psycopg

from .model import ParsedPosting, norm_key


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "ingestion-v1.sql"


class PostgresStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(sql)

    def record_fetch(
        self,
        *,
        source: str,
        url: str,
        final_url: str,
        status: int,
        body: str,
        content_type: str | None,
    ) -> int:
        payload_hash = sha256(body.encode("utf-8")).hexdigest()
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                """
                insert into raw_observation
                    (source_code, requested_url, final_url, http_status, content_type, payload_sha256, payload_text)
                values (%s,%s,%s,%s,%s,%s,%s)
                returning id
                """,
                (source, url, final_url, status, content_type, payload_hash, body),
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
            if current_revision_id:
                previous_hash = conn.execute(
                    "select normalized_content_hash from job_posting_revision where id=%s",
                    (current_revision_id,),
                ).fetchone()[0]

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
                     source_projection_json, normalized_projection_json, raw_observation_id)
                values (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                returning id
                """,
                (
                    posting_id, revision_no, content_hash, parsed.title,
                    json.dumps(parsed.source_specific, ensure_ascii=False),
                    json.dumps(projection, ensure_ascii=False),
                    raw_id,
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
            return {
                "posting_id": posting_id,
                "revision_id": revision_id,
                "revision_no": revision_no,
                "revision_created": True,
                "state": "OBSERVED" if revision_no == 1 else "CHANGED",
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
                (organization_mention_id, organization_id, confidence_band, status, evidence_json)
            values (%s,%s,'LOW','CANDIDATE',%s::jsonb)
            on conflict do nothing
            """,
            (
                mention_id, org_id,
                json.dumps({
                    "epistemic_class": "HYPOTHESIS",
                    "reason": "exact normalized source mention only",
                    "identity_asserted": False,
                }),
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
                        insert into match_candidate(posting_a_id, posting_b_id, reason_json, status)
                        values (%s,%s,%s::jsonb,'OPEN')
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
                "by_source": by_source,
                "lifecycle": lifecycle,
            }
