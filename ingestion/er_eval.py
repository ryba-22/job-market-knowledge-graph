from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import psycopg

from .model import norm_key


GENERATOR_VERSION = "er-eval-v1"


TOKEN_RE = re.compile(r"[a-zA-Z0-9+#.]+", re.U)
SENIORITY = {"junior","mid","middle","senior","lead","staff","principal","intern","trainee"}
LEGAL_SUFFIX_PATTERNS = (
    r"\bspółka z ograniczoną odpowiedzialnością\b",
    r"\bsp\.?\s*z\.?\s*o\.?\s*o\.?\b",
    r"\bspółka komandytowa\b",
    r"\bsp\.?\s*k\.?\b",
    r"\bs\.?\s*a\.?\b",
    r"\bltd\.?\b",
    r"\blimited\b",
)


def _organization_name_signature(value: str) -> str:
    text = norm_key(value)
    text = re.sub(r"[^a-z0-9ąćęłńóśźż]+", " ", text)
    for pattern in LEGAL_SUFFIX_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _title_tokens(title: str) -> set[str]:
    return {x.casefold() for x in TOKEN_RE.findall(title or "") if len(x) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _seniority(tokens: set[str]) -> set[str]:
    return tokens & SENIORITY


def _load_postings(conn):
    rows = conn.execute(
        """
        select
            p.id,
            p.source_code,
            p.source_posting_id,
            p.canonical_source_url,
            r.title_source,
            r.normalized_projection_json,
            om.normalized_mention,
            oc.organization_id
        from job_posting p
        join job_posting_revision r on r.id=p.current_revision_id
        left join organization_mention om on om.job_posting_revision_id=r.id
        left join organization_candidate oc on oc.organization_mention_id=om.id
        order by p.id
        """
    ).fetchall()
    out = []
    for row in rows:
        projection = row[5]
        if isinstance(projection, str):
            projection = json.loads(projection)
        out.append({
            "id": row[0],
            "source": row[1],
            "source_posting_id": row[2],
            "url": row[3],
            "title": row[4] or projection.get("title") or "",
            "projection": projection,
            "org_mention": row[6] or "",
            "organization_id": row[7],
        })
    return out


def _org_domains(conn):
    rows = conn.execute(
        """
        select organization_id, domain, confidence_band
        from organization_domain_candidate
        where status in ('CANDIDATE','VERIFIED')
        """
    ).fetchall()
    out = defaultdict(set)
    for org_id, domain, confidence in rows:
        out[org_id].add(domain)
    return out


def _explicit_identity_evidence(a, b, domains):
    evidence = []
    da = domains.get(a["organization_id"], set()) if a["organization_id"] else set()
    db = domains.get(b["organization_id"], set()) if b["organization_id"] else set()
    shared_domains = sorted(da & db)
    if shared_domains:
        evidence.append({
            "type": "SHARED_EXPLICIT_ORGANIZATION_DOMAIN",
            "direction": "SUPPORTS_SAME",
            "strength": "STRONG",
            "value": shared_domains,
        })
    return evidence


def generate(dsn: str, limit_pairs: int = 200) -> dict:
    with psycopg.connect(dsn) as conn:
        postings = _load_postings(conn)
        domains = _org_domains(conn)
        candidates = []
        for i, a in enumerate(postings):
            for b in postings[i+1:]:
                if a["source"] == b["source"]:
                    continue
                ta, tb = _title_tokens(a["title"]), _title_tokens(b["title"])
                sim = _jaccard(ta, tb)
                same_org_mention = bool(a["org_mention"]) and a["org_mention"] == b["org_mention"]
                org_signature_a = _organization_name_signature(a["org_mention"])
                org_signature_b = _organization_name_signature(b["org_mention"])
                same_org_signature = bool(org_signature_a) and org_signature_a == org_signature_b
                same_org_candidate = (
                    a["organization_id"] is not None
                    and a["organization_id"] == b["organization_id"]
                )
                evidence = _explicit_identity_evidence(a, b, domains)
                shared_domain = any(x["type"] == "SHARED_EXPLICIT_ORGANIZATION_DOMAIN" for x in evidence)
                same_seniority = _seniority(ta) == _seniority(tb)
                seniority_conflict = bool(_seniority(ta) and _seniority(tb) and _seniority(ta) != _seniority(tb))

                if not (same_org_mention or same_org_signature or same_org_candidate or shared_domain or sim >= 0.45):
                    continue

                if same_org_mention and sim == 1.0:
                    stratum = "same_org_exact_title"
                elif same_org_signature and not same_org_mention and sim == 1.0:
                    stratum = "org_legal_suffix_variant_exact_title"
                elif same_org_mention and sim >= 0.55:
                    stratum = "same_org_similar_title"
                elif same_org_candidate and sim >= 0.45:
                    stratum = "same_org_candidate_similar_title"
                elif shared_domain:
                    stratum = "shared_explicit_domain"
                else:
                    stratum = "similar_title_cross_org"

                proposed_label = "UNRESOLVED"
                label_basis = "PENDING"
                # A shared explicit organization domain is identity evidence for the
                # organization, not decisive opportunity identity.
                # v1 deliberately has no AUTO SAME rule without ATS/canonical job URL.
                features = {
                    "title_jaccard": round(sim, 4),
                    "same_org_mention": same_org_mention,
                    "same_org_name_signature": same_org_signature,
                    "org_signature_a": org_signature_a,
                    "org_signature_b": org_signature_b,
                    "same_org_candidate": same_org_candidate,
                    "shared_explicit_domain": shared_domain,
                    "same_seniority_signal": same_seniority,
                    "seniority_conflict": seniority_conflict,
                    "title_a": a["title"],
                    "title_b": b["title"],
                    "source_a": a["source"],
                    "source_b": b["source"],
                    "org_a": a["org_mention"],
                    "org_b": b["org_mention"],
                }
                ranking = (
                    3 if shared_domain else 0,
                    2 if (same_org_mention or same_org_signature) else 0,
                    1 if same_org_candidate else 0,
                    sim,
                )
                candidates.append((ranking, a, b, stratum, features, evidence, proposed_label, label_basis))

        candidates.sort(key=lambda x: x[0], reverse=True)

        # Balanced-ish selection: avoid one stratum consuming the review queue.
        selected = []
        per_stratum = Counter()
        cap_per_stratum = max(10, math.ceil(limit_pairs / 5))
        for item in candidates:
            stratum = item[3]
            if per_stratum[stratum] >= cap_per_stratum:
                continue
            selected.append(item)
            per_stratum[stratum] += 1
            if len(selected) >= limit_pairs:
                break

        created = 0
        for _, a, b, stratum, features, evidence, proposed_label, label_basis in selected:
            x, y = sorted([a["id"], b["id"]])
            row = conn.execute(
                """
                insert into er_eval_pair(
                    posting_a_id, posting_b_id, stratum, features_json,
                    evidence_json, proposed_label, label_basis,
                    review_status, generator_version
                )
                values (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,'PENDING',%s)
                on conflict do nothing
                returning id
                """,
                (
                    x, y, stratum,
                    json.dumps(features, ensure_ascii=False),
                    json.dumps(evidence, ensure_ascii=False),
                    proposed_label, label_basis, GENERATOR_VERSION,
                ),
            ).fetchone()
            if row:
                created += 1
        conn.commit()

        rows = conn.execute(
            """
            select
                e.id, e.stratum, e.proposed_label, e.label_basis,
                e.features_json, e.evidence_json,
                pa.source_code, pa.source_posting_id, pa.canonical_source_url,
                pb.source_code, pb.source_posting_id, pb.canonical_source_url
            from er_eval_pair e
            join job_posting pa on pa.id=e.posting_a_id
            join job_posting pb on pb.id=e.posting_b_id
            where e.generator_version=%s
            order by e.id
            """,
            (GENERATOR_VERSION,),
        ).fetchall()

    corpus = []
    for row in rows:
        corpus.append({
            "pair_id": row[0],
            "stratum": row[1],
            "label": row[2],
            "label_basis": row[3],
            "features": row[4],
            "evidence": row[5],
            "a": {"source": row[6], "source_posting_id": row[7], "url": row[8]},
            "b": {"source": row[9], "source_posting_id": row[10], "url": row[11]},
        })
    summary = {
        "generator_version": GENERATOR_VERSION,
        "postings_considered": len(postings),
        "candidate_pairs_generated": len(candidates),
        "review_pairs_selected": len(corpus),
        "created_now": created,
        "labels": dict(Counter(x["label"] for x in corpus)),
        "strata": dict(Counter(x["stratum"] for x in corpus)),
        "auto_same_count": sum(1 for x in corpus if x["label"] == "SAME_OPPORTUNITY" and x["label_basis"] == "AUTO_DECISIVE"),
        "auto_distinct_count": sum(1 for x in corpus if x["label"] == "DISTINCT_OPPORTUNITY" and x["label_basis"] == "AUTO_COUNTER"),
        "unresolved_count": sum(1 for x in corpus if x["label"] == "UNRESOLVED"),
    }
    return summary, corpus


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--limit-pairs", type=int, default=200)
    parser.add_argument("--summary", default="reports/er-eval-summary.json")
    parser.add_argument("--corpus", default="reports/er-eval-corpus.jsonl")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    summary, corpus = generate(args.dsn, args.limit_pairs)
    sp = Path(args.summary)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cp = Path(args.corpus)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in corpus) + ("\n" if corpus else ""), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
