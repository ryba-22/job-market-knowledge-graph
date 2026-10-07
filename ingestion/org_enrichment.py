from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
from urllib.parse import urlparse

import psycopg

from .versions import ORG_RESOLVER_VERSION


URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
DOMAIN_KEY_HINTS = (
    "website", "webSite", "companyUrl", "employerUrl", "corporateUrl",
    "careersUrl", "careerUrl", "homepage", "sameAs",
)
PROFILE_KEY_HINTS = ("profileUrl", "companyProfile", "employerProfile")


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            yield from _walk(child, next_path)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _walk(child, f"{path}[{idx}]")
    else:
        yield path, value


def _domain(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return None
    if not host or host in {"theprotocol.it", "www.theprotocol.it", "justjoin.it", "www.justjoin.it"}:
        return None
    return host[4:] if host.startswith("www.") else host


def _extract_explicit_urls(source_code: str, source_projection: dict, normalized_projection: dict) -> list[dict]:
    found = []
    for root_name, root in (
        ("source_projection", source_projection),
        ("normalized_projection", normalized_projection),
    ):
        for path, value in _walk(root, root_name):
            if not isinstance(value, str):
                continue
            urls = URL_RE.findall(value)
            if not urls:
                continue
            low_path = path.casefold()
            for url in urls:
                kind = None
                if any(h.casefold() in low_path for h in DOMAIN_KEY_HINTS):
                    kind = "EXPLICIT_ORGANIZATION_URL"
                elif any(h.casefold() in low_path for h in PROFILE_KEY_HINTS):
                    kind = "SOURCE_ORGANIZATION_PROFILE_URL"
                elif "hiringorganization" in low_path:
                    kind = "HIRING_ORGANIZATION_URL"
                if kind:
                    found.append({"type": kind, "url": url, "path": path})
    # stable de-duplication
    unique = {}
    for item in found:
        unique[(item["type"], item["url"], item["path"])] = item
    return list(unique.values())


def enrich(dsn: str) -> dict:
    counts = Counter()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            select
                om.id as mention_id,
                om.mention_text,
                oc.organization_id,
                p.source_code,
                p.source_posting_id,
                r.id as revision_id,
                r.source_projection_json,
                r.normalized_projection_json
            from organization_mention om
            join job_posting_revision r on r.id=om.job_posting_revision_id
            join job_posting p on p.current_revision_id=r.id
            left join organization_candidate oc
              on oc.organization_mention_id=om.id
            order by om.id
            """
        ).fetchall()

        for row in rows:
            mention_id, mention_text, org_id, source_code, source_posting_id, revision_id, source_projection, normalized_projection = row
            if isinstance(source_projection, str):
                source_projection = json.loads(source_projection)
            if isinstance(normalized_projection, str):
                normalized_projection = json.loads(normalized_projection)

            base_value = {"mention": mention_text}
            evidence_id = conn.execute(
                """
                insert into organization_evidence(
                    organization_mention_id, organization_id, evidence_type,
                    direction, strength, epistemic_class, value_json,
                    provenance_json, resolver_version
                )
                values (%s,%s,'SOURCE_ORGANIZATION_MENTION','SUPPORTS_IDENTITY','WEAK','FACT',
                        %s::jsonb,%s::jsonb,%s)
                on conflict do nothing
                returning id
                """,
                (
                    mention_id, org_id,
                    json.dumps(base_value, ensure_ascii=False),
                    json.dumps({
                        "source": source_code,
                        "source_posting_id": source_posting_id,
                        "revision_id": revision_id,
                        "field": "organization_mention",
                    }),
                    ORG_RESOLVER_VERSION,
                ),
            ).fetchone()
            if evidence_id:
                counts["mention_evidence"] += 1

            for item in _extract_explicit_urls(source_code, source_projection or {}, normalized_projection or {}):
                url = item["url"]
                domain = _domain(url)
                strength = "STRONG" if item["type"] in {"EXPLICIT_ORGANIZATION_URL","HIRING_ORGANIZATION_URL"} else "MEDIUM"
                ev = conn.execute(
                    """
                    insert into organization_evidence(
                        organization_mention_id, organization_id, evidence_type,
                        direction, strength, epistemic_class, value_json,
                        provenance_json, resolver_version
                    )
                    values (%s,%s,%s,'SUPPORTS_IDENTITY',%s,'FACT',%s::jsonb,%s::jsonb,%s)
                    on conflict do nothing
                    returning id
                    """,
                    (
                        mention_id, org_id, item["type"], strength,
                        json.dumps({"url": url, "domain": domain}, ensure_ascii=False),
                        json.dumps({
                            "source": source_code,
                            "source_posting_id": source_posting_id,
                            "revision_id": revision_id,
                            "source_path": item["path"],
                        }),
                        ORG_RESOLVER_VERSION,
                    ),
                ).fetchone()
                if ev:
                    counts["url_evidence"] += 1
                    ev_id = ev[0]
                else:
                    ev_row = conn.execute(
                        """
                        select id from organization_evidence
                        where organization_mention_id=%s
                          and evidence_type=%s
                          and value_json=%s::jsonb
                          and resolver_version=%s
                        """,
                        (
                            mention_id, item["type"],
                            json.dumps({"url": url, "domain": domain}, ensure_ascii=False),
                            ORG_RESOLVER_VERSION,
                        ),
                    ).fetchone()
                    ev_id = ev_row[0] if ev_row else None
                if domain and org_id and ev_id:
                    inserted = conn.execute(
                        """
                        insert into organization_domain_candidate(
                            organization_id, domain, status, confidence_band,
                            evidence_id, resolver_version
                        )
                        values (%s,%s,'CANDIDATE',%s,%s,%s)
                        on conflict do nothing
                        returning id
                        """,
                        (
                            org_id, domain,
                            "HIGH" if strength == "STRONG" else "MEDIUM",
                            ev_id, ORG_RESOLVER_VERSION,
                        ),
                    ).fetchone()
                    if inserted:
                        counts["domain_candidates"] += 1
        conn.commit()

        summary = {
            "mentions": len(rows),
            "mention_evidence": conn.execute(
                "select count(*) from organization_evidence where evidence_type='SOURCE_ORGANIZATION_MENTION'"
            ).fetchone()[0],
            "url_evidence": conn.execute(
                "select count(*) from organization_evidence where evidence_type<>'SOURCE_ORGANIZATION_MENTION'"
            ).fetchone()[0],
            "domain_candidates": conn.execute(
                "select count(*) from organization_domain_candidate"
            ).fetchone()[0],
            "verified_domains": conn.execute(
                "select count(*) from organization_domain_candidate where status='VERIFIED'"
            ).fetchone()[0],
        }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--report", default="reports/org-02-summary.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    result = enrich(args.dsn)
    from pathlib import Path
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
