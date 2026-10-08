"""Listing-only IT market discovery; no job detail requests or crawl resume."""
from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

from ingestion.aplikuj_it_scope import is_it_listing_candidate

ROOT = Path('reports/discovery-2026-10-08')
CLIENT_HEADERS={'User-Agent':'Mozilla/5.0 (compatible; JobMarketDiscovery/1.0)','Accept-Language':'pl,en;q=0.8'}

def fetch_aplikuj(page):
    url='https://www.aplikuj.pl/praca/it-informatyka' + (f'/strona-{page}' if page>1 else '')
    with httpx.Client(timeout=25,follow_redirects=True,headers=CLIENT_HEADERS) as c:
        r=c.get(url);r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    text=soup.get_text(' ',strip=True)
    count=re.search(r'(?:Mamy dla Ciebie|Znaleźliśmy)\s+([\d\s]+)\s+ofert',text,re.I)
    results=[]
    for anchor in soup.select('li.offer-card a.offer-title[href]'):
        href=anchor.get('href','')
        m=re.search(r'/oferta/(\d+)(?:/|$)',href)
        if m:
            title=anchor.get_text(' ',strip=True)
            results.append({'id':m.group(1),'title':title,'url':href,'conservative_it':is_it_listing_candidate(title)})
    return {'page':page,'status':r.status_code,'declared':int(count.group(1).replace(' ','')) if count else None,'rows':results}

def listing(label,url):
    try:
        with httpx.Client(timeout=20,follow_redirects=True,headers=CLIENT_HEADERS) as c:
            r=c.get(url)
        s=BeautifulSoup(r.text,'html.parser')
        headers=[h.get_text(' ',strip=True) for h in s.select('h1')]
        visible=' '.join(s.stripped_strings)
        it_count=re.search(r'(?:Mamy dla Ciebie|Znaleźliśmy)\s+([\d\s]+)\s+ofert',visible,re.I)
        return {'status':r.status_code,'url':str(r.url),'h1':headers[:2],'declared':int(it_count.group(1).replace(' ','')) if it_count else None}
    except Exception as exc: return {'error':str(exc)}

def run():
    ROOT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pages=list(pool.map(fetch_aplikuj,range(1,12)))
    by_id={}
    raw_count=0
    for p in pages:
        raw_count+=len(p['rows'])
        for r in p['rows']:
            by_id.setdefault(r['id'],r)
    conserv=sum(x['conservative_it'] for x in by_id.values())
    rejected=[r for r in by_id.values() if not r['conservative_it']]
    accepted=[r for r in by_id.values() if r['conservative_it']]
    summary={
        'as_of_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'listing-only; no offer details; no worker resume',
        'aplikuj':{
            'source':'https://www.aplikuj.pl/praca/it-informatyka',
            'site_declared':pages[0]['declared'],
            'pages_checked':len(pages),
            'page_rows':raw_count,
            'unique_listing_ids':len(by_id),
            'conservative_it_title_signal':conserv,
            'not_automatically_accepted':len(rejected),
            'sample_accepted':accepted[:12],
            'sample_review':[x for x in rejected if re.search(r'it|system|software|danych|informat|teleinformat|wdrozen|informatycz|developer',x['title'],re.I)][:22],
            'per_page':[{'page':p['page'],'site_declared':p['declared'],'listed_cards':len(p['rows'])} for p in pages],
        },
        'teamquest':listing('teamquest','https://teamquest.pl/praca-w-it'),
        'justjoinit':listing('jjit','https://justjoin.it/job-offers/all-locations'),
        'nofluffjobs':listing('ncf','https://nofluffjobs.com/pl/it'),
        'bulldogjob':listing('bulldog','https://bulldogjob.com/companies/jobs'),
    }
    (ROOT/'discovery.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'aplikuj-listing-ids.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in by_id.values()),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':run()
