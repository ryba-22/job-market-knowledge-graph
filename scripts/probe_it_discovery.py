"""Bounded listing-only diagnostic. No individual job offer detail requests."""
from __future__ import annotations
import concurrent.futures
import json
import re
import httpx
from bs4 import BeautifulSoup

SITES = {
    'aplikuj_it': 'https://www.aplikuj.pl/praca/it-informatyka',
    'justjoinit_all': 'https://justjoin.it/job-offers/all-locations',
    'nofluff_pl': 'https://nofluffjobs.com/pl/jobs',
    'nofluff_pl_it': 'https://nofluffjobs.com/pl/IT',
    'rocket_it': 'https://rocketjobs.pl/praca/it',
    'rocket_all': 'https://rocketjobs.pl/',
    'bulldog_it': 'https://bulldogjob.pl/companies/jobs',
    'theprotocol': 'https://theprotocol.it/filtry',
    'solidjobs': 'https://solid.jobs/',
    'teamquest': 'https://teamquest.pl/praca/',
    'itleaders': 'https://it-leaders.pl/oferty-pracy',
    'pracuj_it': 'https://www.pracuj.pl/praca/it%3Bkw',
}

def one(kv):
    name, url = kv
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0 (compatible; JobMarketDiscovery/1.0)'}) as client:
            response=client.get(url)
        soup=BeautifulSoup(response.text,'html.parser')
        for e in soup(['script','style','svg','nav','footer']): e.decompose()
        text=soup.get_text(' ',strip=True)
        patt=re.compile(r'(?:\d[\d\s.,]{0,12}\s*(?:ofert\w*|oglosze\w*|stanowisk\w*|jobs|positions)|(?:ofert\w*|oglosze\w*|jobs)\s*\d[\d\s.,]{0,12})',re.I)
        hits=[re.sub(r'\s+',' ',x)[:95] for x in patt.findall(text)[:18]]
        return dict(source=name,http=response.status_code,final=str(response.url),title=soup.title.get_text(' ',strip=True) if soup.title else '',hits=hits,body_bytes=len(response.content),offers_links=len(soup.select('a[href*="/oferta/"]')),job_links=len(soup.select('a[href*="/job-offer/"]')))
    except Exception as ex:
        return dict(source=name,error=f'{type(ex).__name__}: {ex}')

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(one,SITES.items()):
            print(json.dumps(row,ensure_ascii=False),flush=True)
