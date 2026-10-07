from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
import psycopg


EXTRACTOR_VERSION = "opportunity-evidence-v1"
PORTAL_ROOTS = ("justjoin.it", "theprotocol.it")
ATS_HOST_HINTS = (
    "greenhouse.io", "lever.co", "workdayjobs.com", "myworkdayjobs.com",
    "smartrecruiters.com", "teamtailor.com", "recruitee.com", "ashbyhq.com",
)
APPLICATION_KEY_HINTS = (
    "apply", "application", "applicationurl", "applyurl", "candidateurl",
    "careerurl", "joburl", "externalurl", "redirecturl",
)
REQUISITION_KEY_HINTS = (
    "requisition", "requisitionid", "jobid", "job_id", "vacancyid", "referenceid",
    "reference", "refno", "reqid",
)
CLIENT_RE = re.compile(
    r"\b(?:our client|for our client|dla naszego klienta|dla klienta|client:|klient:)\b",
    re.I,
)
PROJECT_RE = re.compile(
    r"\b(?:project|projekt|o projekcie|about the project)\b",
    re.I,
)


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


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return ""


def _external(url: str) -> bool:
    host = _host(url)
    return bool(host) and not any(host == root or host.endswith("." + root) for root in PORTAL_ROOTS)


def _normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    path = re.sub(r"/+$", "", p.path or "/")
    query = p.query
    return f"{scheme}://{host}{path}" + (f"?{query}" if query else "")


def _ats_identity(url: str) -> dict | None:
    host = _host(url)
    if not host or not any(h in host for h in ATS_HOST_HINTS):
        return None
    p = urlparse(url)
    chunks = [x for x in p.path.split("/") if x]
    query = parse_qs(p.query)
    req = None
    for key in ("jobid","jobId","gh_jid","lever-job-id","requisitionId","reqId"):
        if key in query and query[key]:
            req = str(query[key][0])
            break
    if req is None and chunks:
        req = chunks[-1]
    return {"host": host, "requisition": req, "url": _normalize_url(url)}


def _extract_json_urls(value) -> list[dict]:
    out = []
    for path, child in _walk(value):
        if not isinstance(child, str):
            continue
        low_path = path.casefold()
        if not child.startswith(("http://","https://")):
            continue
        if any(h in low_path for h in APPLICATION_KEY_HINTS):
            out.append({"type":"APPLICATION_URL","url":child,"path":path})
        ats = _ats_identity(child)
        if ats:
            out.append({"type":"ATS_URL","url":child,"path":path,"ats":ats})
    return out


def _extract_json_requisitions(value) -> list[dict]:
    out = []
    for path, child in _walk(value):
        if child in (None,"",[],{}):
            continue
        key = path.split(".")[-1].split("[")[0].casefold()
        if key in REQUISITION_KEY_HINTS or any(h == key for h in REQUISITION_KEY_HINTS):
            sval = str(child).strip()
            if 2 <= len(sval) <= 200:
                out.append({"type":"EXPLICIT_REQUISITION","value":sval,"path":path})
    return out


def _extract_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a.get("href","").strip()
        text = " ".join(a.stripped_strings).casefold()
        if not href.startswith(("http://","https://")):
            continue
        ats = _ats_identity(href)
        if ats:
            out.append({"type":"ATS_URL","url":href,"path":"html.a[href]","ats":ats})
        elif _external(href) and any(x in text for x in ("apply","aplikuj","application","career","job")):
            out.append({"type":"APPLICATION_URL","url":href,"path":"html.a[href]"})
    return out


def _context_signals(text: str) -> list[dict]:
    compact = re.sub(r"\s+"," ",text or "")
    out = []
    for kind, regex in (("CLIENT_SIGNAL",CLIENT_RE),("PROJECT_SIGNAL",PROJECT_RE)):
        for m in regex.finditer(compact):
            s=max(0,m.start()-160); e=min(len(compact),m.end()+320)
            snippet=compact[s:e].strip()
            out.append({"type":kind,"snippet":snippet[:700]})
            if len([x for x in out if x["type"]==kind]) >= 3:
                break
    return out


def _latest_payload(conn, posting_id: int):
    row = conn.execute(
        """
        select ro.payload_text, ro.content_type, ro.id
        from job_posting p
        join job_posting_revision r on r.id=p.current_revision_id
        join raw_observation ro on ro.id=r.raw_observation_id
        where p.id=%s
        """,
        (posting_id,),
    ).fetchone()
    return row


def _extract_for_posting(conn, posting_id: int) -> tuple[list[dict], int | None]:
    row=_latest_payload(conn,posting_id)
    if not row:
        return [],None
    payload, content_type, raw_id=row
    evidence=[]
    parsed=None
    if "json" in (content_type or ""):
        try:
            parsed=json.loads(payload)
        except Exception:
            parsed=None
    if parsed is not None:
        evidence.extend(_extract_json_urls(parsed))
        evidence.extend(_extract_json_requisitions(parsed))
        text=json.dumps(parsed,ensure_ascii=False)
    else:
        evidence.extend(_extract_html(payload))
        text=BeautifulSoup(payload,"html.parser").get_text(" ",strip=True)
    evidence.extend(_context_signals(text))
    unique={}
    for item in evidence:
        key=json.dumps(item,ensure_ascii=False,sort_keys=True)
        unique[key]=item
    return list(unique.values()),raw_id


def enrich(dsn: str) -> dict:
    counts=Counter()
    with psycopg.connect(dsn) as conn:
        pairs=conn.execute(
            """
            select id, posting_a_id, posting_b_id
            from er_eval_pair
            where review_status='PENDING'
            order by id
            """
        ).fetchall()
        for pair_id,a,b in pairs:
            for posting_id in (a,b):
                items,raw_id=_extract_for_posting(conn,posting_id)
                for item in items:
                    et=item["type"]
                    if et=="ATS_URL":
                        direction="SUPPORTS_SAME"; strength="DECISIVE"; cls="FACT"
                    elif et=="EXPLICIT_REQUISITION":
                        direction="SUPPORTS_SAME"; strength="STRONG"; cls="FACT"
                    elif et=="APPLICATION_URL":
                        direction="SUPPORTS_SAME"; strength="STRONG"; cls="FACT"
                    else:
                        direction="NEUTRAL"; strength="MEDIUM"; cls="FACT"
                    row=conn.execute(
                        """
                        insert into opportunity_evidence(
                            er_eval_pair_id, posting_id, evidence_type, direction,
                            strength, epistemic_class, value_json, provenance_json,
                            extractor_version
                        )
                        values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                        on conflict do nothing
                        returning id
                        """,
                        (
                            pair_id,posting_id,et,direction,strength,cls,
                            json.dumps(item,ensure_ascii=False),
                            json.dumps({"raw_observation_id":raw_id},ensure_ascii=False),
                            EXTRACTOR_VERSION,
                        ),
                    ).fetchone()
                    if row:
                        counts[et]+=1
        conn.commit()
        totals=dict(conn.execute(
            "select evidence_type,count(*) from opportunity_evidence group by evidence_type order by evidence_type"
        ).fetchall())
    return {"pairs":len(pairs),"created":dict(counts),"totals":totals}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--report",default="reports/er-eval-02-evidence.json")
    args=p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    result=enrich(args.dsn)
    path=Path(args.report); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
