"""Standalone local reviewer for RI-01. Review state must be explicitly exported."""
from collections import defaultdict
import json


def reviewer_html(packets: list[dict], assertions: list[dict], full_text_by_id: dict[str, str]) -> str:
    grouped = defaultdict(list)
    for assertion in assertions:
        grouped[assertion["posting_id"]].append({
            "assertion_id": assertion["assertion_id"], "quote": assertion["quote"],
            "modality_candidate": assertion["modality_candidate"],
            "category_candidate": assertion["category_candidate"],
            "concept_candidates": assertion["concept_candidates"],
            "source_path": assertion["source_path"],
        })
    rows = []
    for packet in packets:
        p = {k: packet[k] for k in ["posting_id", "source", "title", "company",
              "url", "split", "family_candidate", "seniority_candidate", "language_candidate", "revision_id"]}
        p["full_text"] = full_text_by_id.get(p["posting_id"], "")
        p["candidates"] = grouped[p["posting_id"]]
        rows.append(p)
    # Escape HTML metacharacters in script data; JS parses as JSON safely.
    payload = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return r'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RI-01 · Annotation workbench</title>
<style>
*{box-sizing:border-box}:root{font-family:system-ui,sans-serif;color:#172033;background:#f4f6fa}
body{max-width:1300px;margin:auto;padding:20px}header{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
input,select,textarea,button{font:inherit;padding:8px;border:1px solid #bdc8d5;background:white;border-radius:6px}
button{cursor:pointer}button:hover{background:#eef4fa}a{color:#1656a9}
.notice{padding:14px;background:#fff5e4;border-left:4px solid #b45309;margin:14px 0}
.stats{background:white;padding:12px;border:1px solid #dce3eb;border-radius:8px;margin:10px 0}
.grid{display:grid;grid-template-columns:46% 54%;gap:12px}.panel{background:white;border:1px solid #dce3eb;border-radius:9px;padding:14px;min-height:200px}
.text{white-space:pre-wrap;word-break:break-word;max-height:74vh;overflow-y:auto;font-size:13px;line-height:1.6}
.candidate{border-bottom:1px solid #e5e7eb;padding:10px 2px;word-break:break-word}
.candidate p{font-size:13px;margin:6px 0}.candidate label{display:inline-block;font-size:12px}
small{display:block;color:#64748b;word-break:break-all}.controls{display:flex;gap:9px;flex-wrap:wrap}
#missing{width:100%;min-height:130px}#review-note{width:100%;min-height:54px}
@media(max-width:950px){.grid{grid-template-columns:1fr}.text{max-height:40vh}}
</style></head><body>
<h1>RI-01 — ręczna adjudykacja</h1>
<p class="notice"><b>To nie są gotowe gold labels.</b> REVIEWED oznacza, że recenzent sprawdził cały dokument, wszystkie stwierdzenia oraz brakujące wymagania. Eksport musi zawierać identyfikator recenzenta. Zapis odbywa się lokalnie w przeglądarce i nie aktualizuje repozytorium automatycznie.</p>
<header>
<label>Recenzent <input id="reviewer" placeholder="np. initials / reviewer-01"></label>
<label>Filtr <select id="sourceFilter"><option value="">Wszystkie źródła</option></select></label>
<button id="prev">← Poprzednia</button><button id="next">Następna →</button>
<button id="export">Eksport JSON</button>
<label>Import JSON <input type="file" id="import" accept=".json,application/json"></label>
</header>
<div class="stats"><span id="progress"></span><p id="meta"></p></div>
<div class="grid"><section class="panel"><h2>Dostępny tekst z korpusu (może być niepełny)</h2><div class="text" id="fullText"></div></section>
<section class="panel"><h2>Propozycje ekstraktora <small id="count"></small></h2><div id="candidates"></div>
<h3>Brakujące wymagania</h3>
<p>Jedna brakująca pozycja w linii, format: <code>MUST | dokładny cytat</code>, <code>NICE | cytat</code> lub <code>TASK | cytat</code>. Cytat powinien występować w tekście ogłoszenia.</p>
<textarea id="missing" placeholder="MUST | praktyczna znajomość Linuksa"></textarea>
<h3>Uwagi</h3><textarea id="review-note"></textarea>
<div class="controls"><label><input type="checkbox" id="complete"> Przejrzałem(-am) wszystkie kandydaty i cały tekst oferty</label></div>
</section></div>
<script id="data" type="application/json">''' + payload + r'''</script>
<script>
const postings=JSON.parse(document.getElementById('data').textContent);
let index=0, reviews={};
const $=id=>document.getElementById(id);
function review(p){return reviews[p.posting_id]||(reviews[p.posting_id]={posting_id:p.posting_id,revision_id:p.revision_id,review_status:'IN_PROGRESS',decisions:{},missing:'',notes:''});}
const selectSource=$('sourceFilter');
[...new Set(postings.map(x=>x.source))].sort().forEach(s=>{const op=document.createElement('option');op.value=s;op.textContent=s;selectSource.appendChild(op);});
function visible(){return postings.map((p,i)=>({p,i})).filter(({p})=>!selectSource.value||p.source===selectSource.value);}
function render(){
 const p=postings[index],r=review(p);
 $('meta').textContent=(index+1)+' / '+postings.length+' · '+p.posting_id+' · '+p.title+' · '+p.company+' · '+p.family_candidate+' · '+p.seniority_candidate+' · '+p.language_candidate+' · '+p.split;
 $('fullText').textContent=p.full_text||'(Brak tekstu do kompletnego review. Zachowaj status IN_PROGRESS.)';
 $('count').textContent=p.candidates.length+' kandydatów';
 const dest=$('candidates');dest.replaceChildren();
 p.candidates.forEach((c,i)=>{
  const div=document.createElement('div');div.className='candidate';
  const quote=document.createElement('p');quote.textContent=(i+1)+'. '+c.quote;div.appendChild(quote);
  const info=document.createElement('small');info.textContent=c.modality_candidate+' · '+c.category_candidate+' · '+c.source_path+' · '+c.concept_candidates.join(', ');div.appendChild(info);
  const lab=document.createElement('label');lab.textContent='Ocena: ';
  const sel=document.createElement('select');
  [['','UNREVIEWED'],['ACCEPT','ACCEPT — prawidłowo wydobyte i sklasyfikowane'],['REJECT','REJECT — błędne / niepoprawna klasyfikacja']].forEach(([value,label])=>{const op=document.createElement('option');op.value=value;op.textContent=label;sel.appendChild(op);});
  sel.value=r.decisions[c.assertion_id]||'';sel.addEventListener('change',()=>{r.decisions[c.assertion_id]=sel.value;r.review_status='IN_PROGRESS';$('complete').checked=false;progress();});
  lab.appendChild(sel);div.appendChild(lab);dest.appendChild(div);
 });
 $('missing').value=r.missing;$('review-note').value=r.notes;
 $('complete').checked=r.review_status==='REVIEWED';
 progress();
}
function saveText(){const p=postings[index],r=review(p);r.missing=$('missing').value;r.notes=$('review-note').value;}
function progress(){const done=Object.values(reviews).filter(r=>r.review_status==='REVIEWED').length;$('progress').textContent='Zweryfikowano '+done+'/'+postings.length+' ofert · źródło: zamrożony CORPUS-10';}
function move(step){saveText();const pool=visible();if(!pool.length)return;let i=pool.findIndex(x=>x.i===index);index=pool[(i+step+pool.length)%pool.length].i;render();}
$('prev').onclick=()=>move(-1);$('next').onclick=()=>move(1);
selectSource.onchange=()=>{saveText();const pool=visible();if(pool.length)index=pool[0].i;render();};
$('missing').oninput=saveText;$('review-note').oninput=saveText;
$('complete').onchange=()=>{
 saveText();const p=postings[index],r=review(p);
 if($('complete').checked&&!$('reviewer').value.trim()){alert('Podaj identyfikator recenzenta.');$('complete').checked=false;return;}
 if($('complete').checked&&p.candidates.some(c=>!r.decisions[c.assertion_id])){alert('Oceń wszystkie propozycje (ACCEPT/REJECT).');$('complete').checked=false;return;}
 if($('complete').checked&&!p.full_text){alert('Brak pełnego tekstu do oceny recall.');$('complete').checked=false;return;}
 r.review_status=$('complete').checked?'REVIEWED':'IN_PROGRESS';r.reviewer=$('reviewer').value.trim();progress();
};
$('export').onclick=()=>{saveText();
 const result={format:'ri01-manual-reviews-v1',reviewer:$('reviewer').value.trim(),exported_at:new Date().toISOString(),reviews:Object.values(reviews)};
 const a=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));a.href=url;a.download='ri01-reviews.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
$('import').onchange=async ev=>{try{const data=JSON.parse(await ev.target.files[0].text());if(data.format!=='ri01-manual-reviews-v1'||!Array.isArray(data.reviews))throw Error('Niepoprawny format');reviews=Object.fromEntries(data.reviews.map(r=>[r.posting_id,r]));$('reviewer').value=data.reviewer||'';render();}catch(e){alert('Nie można zaimportować: '+e.message);}};
render();
</script></body></html>'''
