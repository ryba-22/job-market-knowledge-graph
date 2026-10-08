"""Self-contained, *prediction-blinded* local reviewer UI for CLASSIFICATION-03.

No network, server, or tracker. Browser exports explicit JSON and can restore it.
"""
from __future__ import annotations
from html import escape
import json
from pathlib import Path

FAMILIES = [
    "software_engineering", "data_ai", "infrastructure", "security",
    "enterprise_systems", "it_management", "qa_testing", "it_support",
    "tech_sales", "education", "industrial_automation", "telecom_physical",
    "ecommerce_content", "office_admin", "transport_logistics",
    "manufacturing", "marketing", "other", "unknown",
]

TEMPLATE = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CLASSIFICATION-03 — niezależna anotacja | __REVIEWER__</title>
<style>
:root{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#172336;background:#f3f6fa}
*{box-sizing:border-box}body{margin:0}header{background:#17283e;color:#fff;padding:18px 26px}
header h1{font-size:20px;margin:0 0 7px}header p{margin:0;font-size:13px;color:#c9d6e5}
main{max-width:1120px;margin:22px auto;padding:0 16px}.toolbar,.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.toolbar{justify-content:space-between;padding:16px 18px;background:white;border:1px solid #d8e1eb;border-radius:9px}
button{border:1px solid #b4c4d5;border-radius:7px;background:white;padding:10px 15px;cursor:pointer;font-size:14px}
button.primary{background:#1765a3;color:white;border-color:#1765a3}button:hover{filter:brightness(.95)}
input,select,textarea{font:inherit;padding:9px;border:1px solid #b6c3d0;border-radius:6px;background:white}
input[type=text]{min-width:150px}input[type=checkbox]{width:17px;height:17px}
.progress{width:100%;height:9px;background:#e6edf5;border-radius:5px;overflow:hidden;margin-top:12px}
.fill{height:100%;background:#25836c;width:0}
.columns{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(310px,1fr);gap:16px;margin-top:18px}
section{background:white;border:1px solid #d8e1eb;border-radius:9px;padding:20px;min-width:0}
h2{font-size:19px;margin:0 0 10px}.metadata{color:#526377;font-size:13px;margin-bottom:15px}
.description{white-space:pre-wrap;overflow-wrap:anywhere;max-height:68vh;overflow:auto;line-height:1.5;font-size:14px;background:#f7f9fc;padding:17px;border-radius:7px;border:1px solid #e5ebf0}
label{display:block;font-size:14px;font-weight:600;margin:14px 0 5px}
.help{color:#4d6277;font-size:12px;line-height:1.5;margin:8px 0}
textarea{width:100%;min-height:105px;resize:vertical}
#message{font-size:13px;min-height:22px;margin-top:12px;color:#a12222}
.note{margin-top:18px;font-size:12px;color:#526377;line-height:1.5}
.nav-id{font-weight:650;color:#164b80}.radio-grid{display:grid;gap:8px}
.radio-grid label{display:flex;gap:8px;align-items:start;margin:0;font-weight:500;cursor:pointer;padding:8px;border:1px solid #e4e9ef;border-radius:5px}
.radio-grid input{margin-top:3px;flex-shrink:0}
@media(max-width:800px){.columns{grid-template-columns:1fr}.description{max-height:44vh}}
</style></head><body>
<header><h1>CLASSIFICATION-03 · przegląd źródeł · __REVIEWER__</h1>
<p>Zaślepiona anotacja: pokazujemy pełny tekst ogłoszenia, nie decyzję ani uzasadnienie klasyfikatora. Nie korzystaj z wyników CLASSIFICATION-02 podczas oznaczania.</p></header>
<main>
<div class="toolbar">
<div><strong id="progressText"></strong><div class="help">Etykiety zapisują się w tym widoku roboczo. Eksportuj plik przed jego zamknięciem.</div></div>
<div class="controls"><input id="reviewer" type="text" placeholder="Identyfikator recenzenta" autocomplete="off">
<button type="button" id="importBtn">Import zapisanej pracy</button>
<input id="importFile" type="file" accept=".json" hidden>
<button type="button" class="primary" id="exportBtn">Eksport JSON</button></div>
<div class="progress"><div class="fill" id="bar"></div></div>
</div>
<div class="columns">
<section><div class="metadata"><span id="position"></span> · <span class="nav-id" id="postId"></span> · Aplikuj.pl · <span id="industry"></span></div>
<h2 id="title"></h2><div class="description" id="description"></div>
<p class="note">Dowód powinien być dosłownym fragmentem tytułu, kategorii lub opisu. Wybierz tylko taki zakres stanowiska, który uzasadniają obowiązki. Sama branża firmy i znajomość narzędzia nie wystarczają.</p>
<p class="metadata">Źródło: <a id="url" target="_blank" rel="noreferrer noopener">oryginalne ogłoszenie</a></p></section>
<section>
<h2>Ocena niezależna</h2>
<div class="radio-grid">
<label><input type="radio" name="verdict" value="IT_TECHNICAL"> Techniczne IT (software, dane, infrastruktura, security, IT systems)</label>
<label><input type="radio" name="verdict" value="NON_IT"> Poza zakresem technicznego IT</label>
<label><input type="radio" name="verdict" value="IT_ADJACENT"> Rola mieszana / graniczna / IT-adjacent</label>
<label><input type="radio" name="verdict" value="UNDETERMINABLE"> Niewystarczająca lub sprzeczna treść</label>
</div>
<label for="family">Rodzina rzeczywiście wykonywanej pracy</label>
<select id="family"><option value="">Wybierz rodzinę</option>__FAMILY_OPTIONS__</select>
<label for="field">Pole z dowodem</label>
<select id="field"><option value="">Wybierz pole</option><option value="title">Tytuł</option><option value="description">Opis stanowiska</option><option value="source_industry">Kategoria źródła (pomocniczo)</option></select>
<label for="quote">Dosłowny fragment źródła</label><textarea id="quote" placeholder="Wklej maks. 240 znaków potwierdzających interpretację roli; dla IT i non-IT wymagany"></textarea>
<label for="notes">Uzasadnienie / niepewność</label>
<textarea id="notes" placeholder="W szczególności role graniczne, niejasności, niewystarczający opis."></textarea>
<div class="controls"><button id="prev">← Poprzednia</button><button class="primary" id="next">Zapisz i następna →</button></div>
<div id="message" role="status" aria-live="polite"></div>
<div class="note">
<label style="display:flex;align-items:start;gap:8px;font-weight:500"><input type="checkbox" id="attest"> Potwierdzam, że oceniam źródła samodzielnie i nie używam etykiet modelu ani cudzych wyników anotacji.</label>
<p>Nie publikuj opisów ofert z archiwum. Eksport zawiera jedynie decyzję, źródłowe ID i krótki dowód.</p></div>
</section>
</div></main>
<script type="application/json" id="sample">__SAMPLE__</script>
<script>
"use strict";
const packet = JSON.parse(document.getElementById("sample").textContent);
const items = packet.items, byId = Object.fromEntries(items.map(x=>[x.posting_id,x]));
const decisions = {}; let current=0;
const $ = id=>document.getElementById(id);
function clean(s){return (s||"").replace(/\\s+/g," ").trim();}
function valid(a, row){
 if (!a || !["IT_TECHNICAL","NON_IT","IT_ADJACENT","UNDETERMINABLE"].includes(a.label)) return "Wybierz jedno rozstrzygnięcie.";
 if(!a.family) return "Wybierz rodzinę pracy.";
 if (a.label==="IT_TECHNICAL" || a.label==="NON_IT"){
   if (!a.quote || a.quote.length<5 || a.quote.length>240) return "Dosłowny fragment (5–240 znaków) jest wymagany.";
   if(!a.evidence_field) return "Wybierz pole źródła z dowodem.";
   if(a.label==="IT_TECHNICAL" && a.evidence_field!=="description") return "Potwierdzenie technicznej pracy IT wymaga fragmentu z opisu obowiązków/wymagań, nie samego tytułu.";
 }
 if(a.label==="IT_ADJACENT" || a.label==="UNDETERMINABLE"){
   if(!a.notes || a.notes.trim().length<12) return "Wyjaśnij niejednoznaczność (min. 12 znaków).";
 }
 if(a.quote) {
   if(!a.evidence_field) return "Wybierz pole cytatu.";
   if (!clean(row[a.evidence_field]).includes(clean(a.quote))) return "Cytat nie występuje dosłownie w wybranym polu; skopiuj fragment tekstu.";
 }
 return "";
}
function readForm(){
 const row=items[current];
 const selected=document.querySelector('input[name="verdict"]:checked');
 return {posting_id:row.posting_id,revision_id:row.revision_id,raw_payload_sha256:row.raw_payload_sha256,
         label:selected?.value||"",family:$("family").value,evidence_field:$("field").value,
         quote:$("quote").value.trim(),notes:$("notes").value.trim()};
}
function remember(){
 const a=readForm();const error=valid(a,items[current]);
 if(error){$("message").textContent=error;return false;}
 decisions[a.posting_id]=a;$("message").textContent="Ocena zapisana w tym widoku.";updateProgress();return true;
}
function updateProgress(){
 $("progressText").textContent=Object.keys(decisions).length+" / "+items.length+" ukończonych";
 $("bar").style.width=(Object.keys(decisions).length/items.length*100).toFixed(1)+"%";
}
function show(i){
 current=Math.max(0,Math.min(items.length-1,i));const r=items[current],a=decisions[r.posting_id]||{};
 $("position").textContent=(current+1)+"/"+items.length;$("postId").textContent="#"+r.posting_id;
 $("industry").textContent=r.source_industry||"Brak kategorii";
 $("title").textContent=r.title;
 $("description").textContent=r.description;
 $("url").href=r.source_url;
 document.querySelectorAll('input[name="verdict"]').forEach(x=>x.checked=x.value===a.label);
 $("family").value=a.family||"";$("field").value=a.evidence_field||"";
 $("quote").value=a.quote||"";$("notes").value=a.notes||"";
 $("message").textContent="";
 $("prev").disabled=current===0;
 $("next").textContent=current===items.length-1?"Zapisz ostatnią ocenę":"Zapisz i następna →";
 updateProgress();
}
$("next").onclick=()=>{if(remember()){show(current+1);}};
$("prev").onclick=()=>{if(!decisions[items[current].posting_id]){if(!remember())return;}else{remember();}show(current-1);};
$("exportBtn").onclick=()=>{
 if(!$("reviewer").value.trim()){$("message").textContent="Wpisz identyfikator recenzenta.";return;}
 if(!$("attest").checked){$("message").textContent="Potwierdź niezależność przeglądu.";return;}
 const entry=readForm();if(entry.label && valid(entry,items[current])==="") decisions[entry.posting_id]=entry;
 const output={format:"classification03-annotations-v1",reviewer:$("reviewer").value.trim(),
  independent_attested:true,round:packet.round,annotations:Object.values(decisions)};
 const blob=new Blob([JSON.stringify(output,null,2)],{type:"application/json"});
 const link=document.createElement("a");link.href=URL.createObjectURL(blob);
 link.download="classification03-"+packet.round+"-"+$("reviewer").value.trim().replace(/[^a-z0-9_-]/gi,"-")+".json";
 link.click();setTimeout(()=>URL.revokeObjectURL(link.href),2000);updateProgress();
};
$("importBtn").onclick=()=>$("importFile").click();
$("importFile").onchange=async(e)=>{
 try{
 const file=e.target.files[0]; if(!file)return;
 const incoming=JSON.parse(await file.text());
 if(incoming.format!=="classification03-annotations-v1"||incoming.round!==packet.round)throw Error("Niewłaściwy format lub runda.");
 if(!Array.isArray(incoming.annotations))throw Error("Brak tablicy anotacji.");
 const next={};
 for(const a of incoming.annotations) {
  const row=byId[a.posting_id];
  if(!row||a.revision_id!==row.revision_id||a.raw_payload_sha256!==row.raw_payload_sha256)
    throw Error("Nieznane ID lub inna rewizja: "+a.posting_id);
  const err=valid(a,row);if(err)throw Error(a.posting_id+": "+err);
  if(next[a.posting_id])throw Error("Powtórzony ID");
  next[a.posting_id]=a;
 }
 Object.keys(decisions).forEach(key=>delete decisions[key]);
 Object.assign(decisions,next);$("reviewer").value=incoming.reviewer||"";
 $("attest").checked=!!incoming.independent_attested;show(current);
 }catch(err){$("message").textContent=String(err.message||err);}
 e.target.value="";
};
show(0);
</script></body></html>"""


def write_reviewers(root: Path):
    family_options = "".join('<option value="'+escape(x)+'">'+escape(x.replace("_"," "))+"</option>"
                             for x in FAMILIES)
    for round in ("a", "b", "c", "human"):
        path = root / f"reviewer-{round}.jsonl"
        if not path.exists():
            continue
        items = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
        # JSON is embedded in a non-executable element. Reject literal HTML
        # closing tag material and Unicode JS line breaks.
        packed = json.dumps({"round":round, "items":items}, ensure_ascii=False)
        packed = packed.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        packed = packed.replace("\u2028","\\u2028").replace("\u2029","\\u2029")
        output = (TEMPLATE.replace("__REVIEWER__", round.upper())
                  .replace("__FAMILY_OPTIONS__", family_options).replace("__SAMPLE__", packed))
        (root / f"reviewer-{round}.html").write_text(output, encoding="utf-8")
