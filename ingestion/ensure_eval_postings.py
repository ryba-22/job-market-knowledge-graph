from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
import psycopg

from .sources import ADAPTERS
from .storage import PostgresStore
from .theprotocol_mcp import fetch_offers_by_ids_sync, parse as parse_theprotocol
from .versions import PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS


ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS=ROOT/"data"/"evals"/"er-eval-02-reviewer-decisions.json"
RUN_ID="er-eval-02-required-postings"


def _required(payload):
    seen=set()
    out=[]
    for d in payload["decisions"]:
        for side in ("a","b"):
            key=(d[side]["source"],d[side]["source_posting_id"])
            if key not in seen:
                seen.add(key); out.append(key)
    return out


def _present(conn, source, sid):
    return bool(conn.execute(
        "select 1 from job_posting where source_code=%s and source_posting_id=%s",
        (source,sid),
    ).fetchone())


def _ingest_jjit(store, client, sid):
    url=f"https://justjoin.it/job-offer/{sid}"
    response=client.get(url); response.raise_for_status()
    parsed=ADAPTERS["justjoinit"].parse_detail(response.text,str(response.url))
    raw_id=store.record_fetch(
        source="justjoinit",url=url,final_url=str(response.url),
        status=response.status_code,body=response.text,
        content_type=response.headers.get("content-type"),
        run_id=RUN_ID,source_posting_id=sid,
        parser_version=PARSER_BUNDLE_VERSION,
        transport_version=TRANSPORT_VERSIONS["justjoinit"],
    )
    result=store.ingest(parsed,raw_id)
    return {"source":"justjoinit","source_posting_id":sid,"state":result["state"],"url":parsed.url}


def _ingest_tp(store, sid, pair):
    search,details=pair
    parsed=parse_theprotocol(search,details)
    raw_text=json.dumps({"search":search,"details":details},ensure_ascii=False,sort_keys=True)
    target=parsed.url or f"mcp://theprotocol/{sid}"
    raw_id=store.record_fetch(
        source="theprotocol",url=target,final_url=target,status=200,
        body=raw_text,content_type="application/json; transport=official-mcp",
        run_id=RUN_ID,source_posting_id=sid,
        parser_version=PARSER_BUNDLE_VERSION,
        transport_version=TRANSPORT_VERSIONS["theprotocol"],
    )
    result=store.ingest(parsed,raw_id)
    return {"source":"theprotocol","source_posting_id":sid,"state":result["state"],"url":parsed.url}


def ensure(dsn: str, decisions_path: Path):
    payload=json.loads(decisions_path.read_text(encoding="utf-8"))
    required=_required(payload)
    with psycopg.connect(dsn) as conn:
        missing=[x for x in required if not _present(conn,*x)]
    if not missing:
        return {"required":len(required),"missing_before":0,"added":[]}

    store=PostgresStore(dsn)
    store.begin_run(RUN_ID,trigger_kind="eval-required",source_scope="reviewer-fixture")
    added=[]
    tp_ids=[sid for source,sid in missing if source=="theprotocol"]
    tp_found=fetch_offers_by_ids_sync(tp_ids,max_pages=20) if tp_ids else {}
    with httpx.Client(timeout=30,follow_redirects=True,headers={"User-Agent":"job-market-knowledge-graph/ER-EVAL-02"}) as client:
        for source,sid in missing:
            if source=="justjoinit":
                added.append(_ingest_jjit(store,client,sid))
            elif source=="theprotocol":
                pair=tp_found.get(sid)
                if not pair:
                    raise RuntimeError(f"required The Protocol posting not found in MCP search pages: {sid}")
                added.append(_ingest_tp(store,sid,pair))
            else:
                raise RuntimeError(f"unsupported required source: {source}")
    store.finish_run(RUN_ID,status="COMPLETED",summary={"added":added})
    return {"required":len(required),"missing_before":len(missing),"added":added}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dsn",default=os.environ.get("DATABASE_URL"))
    p.add_argument("--decisions",default=str(DEFAULT_DECISIONS))
    p.add_argument("--report",default="reports/er-eval-02-required-postings.json")
    args=p.parse_args()
    if not args.dsn: raise SystemExit("DATABASE_URL/--dsn required")
    result=ensure(args.dsn,Path(args.decisions))
    out=Path(args.report); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
