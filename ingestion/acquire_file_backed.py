from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time

import httpx

from .expansion_sources import SOURCES
from .model import PostingRef, SourceGoneError
from .retry import RetryPolicy, run_with_retry
from .sources import ADAPTERS
from .versions import NORMALIZER_VERSION, PARSER_BUNDLE_VERSION, TRANSPORT_VERSIONS


def _load_rows(plan_path: str, source: str, chunk_index: int):
    plan=json.loads(Path(plan_path).read_text(encoding='utf-8'))
    for chunk in plan['chunks']:
        if chunk['source']==source and int(chunk['chunk_index'])==chunk_index:
            return chunk['rows']
    raise KeyError(f'chunk not found: {source}:{chunk_index}')


def _write_jsonl_gz(path: Path, rows):
    raw=('\n'.join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':')) for r in rows)+'\n').encode('utf-8')
    comp=gzip.compress(raw,compresslevel=9,mtime=0)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(comp)
    return {
        'rows':len(rows),
        'uncompressed_bytes':len(raw),
        'compressed_bytes':len(comp),
        'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),
        'compressed_sha256':hashlib.sha256(comp).hexdigest(),
    }


def acquire(plan_path: str, source: str, chunk_index: int, out_dir: str, raw_dir: str, delay: float, max_attempts: int = 4):
    rows=_load_rows(plan_path,source,chunk_index)
    if source == "aplikuj":
        plan_scope = json.loads(Path(plan_path).read_text(encoding="utf-8")).get("aplikuj_scope")
        if plan_scope != "technical-it-v1":
            raise RuntimeError("REFUSED: Aplikuj requires technical-it-v1 category-scoped plan")
    adapter=ADAPTERS[source] if source in ADAPTERS else SOURCES[source]
    corpus=[]
    raw_rows=[]
    gone=[]
    errors=[]
    excluded_non_it=[]
    now=datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=45,follow_redirects=True,headers={'User-Agent':'job-market-knowledge-graph/file-backed-local','Accept-Language':'pl,en;q=0.8'}) as client:
        for row in rows:
            ref=PostingRef(source,row['url'],str(row['source_posting_id']))
            try:
                attempt_errors=[]
                def fetch():
                    if source in ADAPTERS:
                        response=client.get(ref.url)
                        response.raise_for_status()
                        return response.text,str(response.url),response.status_code,response.headers.get('content-type','')
                    return adapter.fetch_detail(client,ref)
                def on_attempt_failure(attempt_no,exc,will_retry,failure_type,http_status):
                    attempt_errors.append({
                        'attempt_no':attempt_no,
                        'failure_type':failure_type,
                        'http_status':http_status,
                        'will_retry':will_retry,
                        'error':f'{type(exc).__name__}: {exc}',
                    })
                try:
                    (payload,final_url,status,content_type),attempt_no=run_with_retry(
                        fetch,
                        policy=RetryPolicy(max_attempts=max_attempts,base_delay_seconds=5.0 if source=='eurotechjobs' else 0.75),
                        on_attempt_failure=on_attempt_failure,
                    )
                except httpx.HTTPStatusError as exc:
                    status=exc.response.status_code
                    if status in (404,410):
                        body=exc.response.text
                        payload_bytes=body.encode('utf-8')
                        payload_sha=hashlib.sha256(payload_bytes).hexdigest()
                        raw_rows.append({
                            'source':source,
                            'source_posting_id':ref.source_posting_id,
                            'requested_url':ref.url,
                            'final_url':str(exc.response.url),
                            'http_status':status,
                            'content_type':exc.response.headers.get('content-type',''),
                            'payload_sha256':payload_sha,
                            'payload_text':body,
                            'run_id':f'file-backed-{source}-{chunk_index}',
                            'parser_version':PARSER_BUNDLE_VERSION,
                            'transport_version':TRANSPORT_VERSIONS[source],
                            'archive_key':f'local:{source}:{ref.source_posting_id}:{payload_sha}',
                            'fetched_at':now,
                            'attempt_errors':attempt_errors,
                        })
                        gone.append({'source_posting_id':ref.source_posting_id,'url':ref.url,'reason':f'HTTP_{status}'})
                        time.sleep(delay)
                        continue
                    raise
                payload_bytes=payload.encode('utf-8')
                payload_sha=hashlib.sha256(payload_bytes).hexdigest()
                raw_rows.append({
                    'source':source,
                    'source_posting_id':ref.source_posting_id,
                    'requested_url':ref.url,
                    'final_url':final_url,
                    'http_status':status,
                    'content_type':content_type,
                    'payload_sha256':payload_sha,
                    'payload_text':payload,
                    'run_id':f'file-backed-{source}-{chunk_index}',
                    'parser_version':PARSER_BUNDLE_VERSION,
                    'transport_version':TRANSPORT_VERSIONS[source],
                    'archive_key':f'local:{source}:{ref.source_posting_id}:{payload_sha}',
                    'fetched_at':now,
                    'fetch_attempts':attempt_no,
                    'attempt_errors':attempt_errors,
                })
                parsed=adapter.parse_detail(payload,final_url) if source in ADAPTERS else adapter.parse_detail(payload,ref)
                if source == "aplikuj":
                    from .aplikuj_it_scope import is_technical_it
                    if not is_technical_it(parsed.title, parsed.source_specific.get("industry")):
                        raw_rows.pop()  # do not retain non-IT details in the cache
                        excluded_non_it.append(parsed.source_posting_id)
                        continue
                projection=parsed.normalized_projection()
                revision_hash=parsed.normalized_hash()
                corpus.append({
                    'source':source,
                    'source_posting_id':parsed.source_posting_id,
                    'url':parsed.url,
                    'revision_id':f'local-{source}-{parsed.source_posting_id}-{revision_hash[:16]}',
                    'title':parsed.title,
                    'source_projection':parsed.source_specific,
                    'normalized_projection':projection,
                    'normalized_projection_hash':revision_hash,
                    'parser_version':PARSER_BUNDLE_VERSION,
                    'normalizer_version':NORMALIZER_VERSION,
                    'raw_payload_sha256':payload_sha,
                    'raw_payload_bytes':len(payload_bytes),
                    'transport_version':TRANSPORT_VERSIONS[source],
                    'archive_key':f'local:{source}:{parsed.source_posting_id}:{payload_sha}',
                    'organization_mention':parsed.company_mention,
                    'organization_mention_normalized':(parsed.company_mention or '').casefold() or None,
                })
            except SourceGoneError as exc:
                gone.append({'source_posting_id':ref.source_posting_id,'url':ref.url,'reason':str(exc)})
            except Exception as exc:
                errors.append({'source_posting_id':ref.source_posting_id,'url':ref.url,'error':f'{type(exc).__name__}: {exc}'})
            time.sleep(delay)
    corpus.sort(key=lambda r:(r['source'],r['source_posting_id']))
    out=Path(out_dir); raw_out=Path(raw_dir)
    corpus_meta=_write_jsonl_gz(out/'corpus.jsonl.gz',corpus)
    raw_meta=_write_jsonl_gz(raw_out/'raw-observations.jsonl.gz',raw_rows)
    manifest={
        'format':'file-backed-market-corpus-v1',
        'source':source,
        'planned':len(rows),
        'postings':len(corpus),
        'source_gone':len(gone),
        'excluded_non_it':len(excluded_non_it),
        'scope':'technical-it-v1' if source=='aplikuj' else None,
        'errors':errors,
        'by_source':{source:len(corpus)} if corpus else {},
        'corpus':corpus_meta,
        'raw_archive':raw_meta,
        'raw_archive_location':str(raw_out/'raw-observations.jsonl.gz'),
        'transport_version':TRANSPORT_VERSIONS[source],
    }
    out.mkdir(parents=True,exist_ok=True)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'source-gone.json').write_text(json.dumps(gone,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',required=True)
    p.add_argument('--source',required=True)
    p.add_argument('--chunk-index',type=int,required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--raw-out',required=True)
    p.add_argument('--delay',type=float,default=0.25)
    p.add_argument('--max-attempts',type=int,default=4)
    args=p.parse_args()
    print(json.dumps(acquire(args.plan,args.source,args.chunk_index,args.out,args.raw_out,args.delay,args.max_attempts),ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
