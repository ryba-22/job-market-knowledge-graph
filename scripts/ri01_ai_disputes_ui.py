#!/usr/bin/env python3
"""Local-only shortlist UI for unresolved AI-vs-extractor disputes."""
import html
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/".local-evidence/ri01/ai-review"


def render(queue: list[dict]) -> str:
    data=json.dumps(queue,ensure_ascii=False).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    header="""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<title>RI-01 · Decyzje sporne</title>
<style>
:root{font-family:system-ui,sans-serif;background:#f5f7fa;color:#1e293b}body{max-width:1050px;margin:auto;padding:24px}
article{background:white;padding:20px;border:1px solid #e2e8f0;border-radius:14px;margin:16px 0}
h1{margin-bottom:0}p{line-height:1.5}button,select,input,textarea{padding:9px;border:1px solid #bcc7d4;border-radius:7px;font:inherit}
.toolbar{position:sticky;top:0;background:#f5f7fa;padding:14px 0;display:flex;gap:10px;flex-wrap:wrap}
label{display:block;margin:7px 0}textarea{width:100%;min-height:52px}
.quote{background:#f8fafc;border-left:3px solid #64748b;padding:12px;overflow-wrap:anywhere}
.meta{color:#64748b;font-size:13px}.warning{background:#fff7ed;padding:14px;border-left:4px solid #f59e0b}
a{color:#1558bb}.tag{font-size:12px;border-radius:5px;background:#e2e8f0;padding:4px 6px}
</style></head><body>
<h1>RI-01 — spory do adjudykacji</h1>
<p class="warning">To nie jest zatwierdzony goldset. Decyzje w tej stronie są opinią recenzenta. Eksportuj wynik przed zamknięciem; strona niczego nie zapisuje do repo automatycznie. Sprawdź oryginalną ofertę przed zatwierdzeniem.</p>
<div class="toolbar"><input id="reviewer" placeholder="Identyfikator recenzenta">
<select id="priority"><option value="P0">P0 — krytyczne</option><option value="P1">P1 — ważne</option><option value="">Wszystkie</option></select>
<button id="export">Eksportuj decyzje JSON</button><span id="count"></span></div>
<div id="content"></div>
<script id="payload" type="application/json">"""
    end="""</script><script>
const data=JSON.parse(document.querySelector('#payload').textContent);
const decisions={};const panel=document.getElementById('content');
const esc=s=>String(s==null?'':s);
function view(){
 const filter=document.getElementById('priority').value;
 let selected=data.filter(x=>!filter||x.priority===filter).slice(0,300);
 document.getElementById('count').textContent=selected.length+' przypadków';
 panel.replaceChildren();
 selected.forEach((item,i)=>{
  let section=document.createElement('article');
  let h=document.createElement('h3');h.textContent=(i+1)+'. '+item.title+' · '+item.priority;section.appendChild(h);
  let meta=document.createElement('p');meta.className='meta';meta.textContent=item.posting_id+' · '+item.source;section.appendChild(meta);
  let link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Otwórz źródło';section.appendChild(link);
  let quote=document.createElement('p');quote.className='quote';quote.textContent=item.quote;section.appendChild(quote);
  let issue=document.createElement('p');issue.textContent='Model: '+item.model_label+' | Ekstraktor: '+item.extractor_labels.join(', ')+' | Powody: '+item.reasons.join(', ');section.appendChild(issue);
  let sel=document.createElement('select');
  const opts=[['','Nierozstrzygnięte'],['MUST','MUST'],['NICE','NICE'],['TASK','TASK'],['UNKNOWN','UNKNOWN'],['REJECT','Odrzuć / nie jest wymaganiem'],['NEEDS_SOURCE','Nie można ocenić bez pełnego źródła']];
  opts.forEach(([val,text])=>{let op=document.createElement('option');op.value=val;op.textContent=text;sel.appendChild(op)});
  const key=item.posting_id+'|'+item.quote+'|'+item.model_label;
  sel.value=decisions[key]?.decision||'';
  sel.onchange=()=>{decisions[key]={posting_id:item.posting_id,quote:item.quote,model:item.model_label,decision:sel.value,notes:decisions[key]?.notes||'',priority:item.priority};};
  section.appendChild(sel);
  let note=document.createElement('textarea');note.placeholder='Uzasadnienie decyzji / korekta ekstraktora';
  note.value=decisions[key]?.notes||'';
  note.oninput=()=>{decisions[key]={posting_id:item.posting_id,quote:item.quote,model:item.model_label,decision:sel.value,notes:note.value,priority:item.priority};};
  section.appendChild(note);
  panel.appendChild(section);
 });
}
document.getElementById('priority').onchange=view;
document.getElementById('export').onclick=()=>{
const payload={format:'ri01-dispute-review-v1',reviewer:document.getElementById('reviewer').value.trim(),origin:'model-assisted-triage',decisions:Object.values(decisions)};
if(!payload.reviewer){alert('Wpisz identyfikator recenzenta.');return}
const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
const a=document.createElement('a');a.href=url;a.download='ri01-dispute-decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
view();
</script></body></html>"""
    return header+data+end


def main():
    cases=[json.loads(s) for s in (WORK/"escalation-queue.jsonl").open(encoding="utf-8")]
    result=WORK/"disputes.html"
    result.write_text(render(cases),encoding="utf-8")
    print(json.dumps({"html":str(result),"cases":len(cases),"priorities":dict(Counter(c["priority"] for c in cases))},ensure_ascii=False))


if __name__=="__main__":
    main()
