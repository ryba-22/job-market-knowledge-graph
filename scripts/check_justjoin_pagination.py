"""Small listing-only pagination probe (not a bulk crawler)."""
import json
import httpx
from bs4 import BeautifulSoup
u='https://justjoin.it/job-offers/all-locations'
paths={'base':u,'page2':u+'?page=2','page30':u+'?page=30','page31':u+'?page=31','from100':u+'?from=100'}
rows={}
with httpx.Client(timeout=25,follow_redirects=True) as c:
 for name,url in paths.items():
  r=c.get(url)
  s=BeautifulSoup(r.text,'html.parser')
  links=[a.get('href') for a in s.select('a[href*="/job-offer/"]')]
  ids=list(dict.fromkeys(x for x in links if x))
  rows[name]={'status':r.status_code,'h1':[h.get_text(' ',strip=True) for h in s.select('h1')][-1:],'raw_links':len(links),'unique_ids':len(ids),'example_ids':ids[:2]}
  rows[name]['ids']=set(ids)
for k,v in rows.items():
 print(k,'http',v['status'],'h1',v['h1'],'links',v['raw_links'],'unique',v['unique_ids'],'sample',v['example_ids'],'overlap_first_page',len(v['ids']&rows['base']['ids']))
with open('reports/discovery-2026-10-08/justjoin-pagination.json','w') as f:
 json.dump({k:{kk:vv for kk,vv in v.items() if kk!='ids'}|{'overlap_base':len(v['ids']&rows['base']['ids'])} for k,v in rows.items()},f,indent=2)
